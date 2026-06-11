"""Sync<->async bridge to a stdio MCP server (method B: wrapper-in-front).

The evidence wrappers (contract 04) are sync tools called from inside the
orchestrator's async loop. The MCP client is async, and spawning the server per
call (npx cold start ~seconds) is wasteful. So this bridge runs ONE daemon thread
with its own asyncio loop, opens the MCP stdio session there once, and lets sync
callers submit coroutines via run_coroutine_threadsafe.

- Lazy: the server process is spawned on first use, never at import.
- Reused: one server process per bridge for the process lifetime.
- Safe: failures raise; callers decide to fall back to direct ES or surface an
  evidence error envelope.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any, Optional

log = logging.getLogger("launchpilot.mcp")

_DEFAULT_TIMEOUT = 30.0


class McpBridge:
    """A persistent stdio MCP session usable from synchronous code."""

    def __init__(self, command: str, args: list[str], env: Optional[dict[str, str]] = None,
                 startup_timeout: float = 120.0):
        self._command = command
        self._args = args
        self._env = env
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session = None  # mcp.ClientSession
        self._stop: Optional[asyncio.Event] = None
        self._ready = threading.Event()
        self._start_error: Optional[BaseException] = None
        self._thread = threading.Thread(target=self._run, name="mcp-bridge", daemon=True)
        self._thread.start()
        # Block until the session is initialized (or failed). First run may include
        # an npx package download, so allow a generous startup window.
        self._ready.wait(timeout=startup_timeout)
        if self._start_error is not None:
            raise self._start_error
        if self._session is None:
            raise RuntimeError("McpBridge: session did not initialize in time")

    def _run(self) -> None:
        # Dedicated event loop hosting the long-lived MCP session.
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        # Open, serve, AND close the session all in ONE task. anyio's stdio_client
        # cancel scope must be exited in the same task it was entered, so close
        # cannot run from a separately-submitted coroutine.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stop = asyncio.Event()
        params = StdioServerParameters(command=self._command, args=self._args, env=self._env)
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    log.info("MCP bridge ready: %s %s", self._command, " ".join(self._args))
                    self._ready.set()
                    await self._stop.wait()  # serve until close() is called
        except BaseException as exc:  # noqa: BLE001 - report to constructor / log
            if not self._ready.is_set():
                self._start_error = exc
                self._ready.set()
            else:
                log.warning("MCP bridge session ended: %s", exc)

    def _submit(self, coro) -> Future:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def list_tools(self, timeout: float = _DEFAULT_TIMEOUT) -> list[str]:
        result = self._submit(self._session.list_tools()).result(timeout=timeout)
        return [t.name for t in result.tools]

    def call(self, tool: str, args: dict[str, Any], timeout: float = _DEFAULT_TIMEOUT) -> Any:
        """Call an MCP tool and return its result (CallToolResult)."""
        return self._submit(self._session.call_tool(tool, args)).result(timeout=timeout)

    def close(self) -> None:
        if self._loop is None or self._stop is None:
            return
        # Signal _serve to exit; it closes the session in its own task, then the
        # loop stops on its own (run_until_complete returns).
        self._loop.call_soon_threadsafe(self._stop.set)
