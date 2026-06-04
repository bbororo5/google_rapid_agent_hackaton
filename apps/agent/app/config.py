"""Runtime settings loaded from environment.

Two modes are derived, not configured directly:
- LLM:      real ADK/Gemini when GEMINI_API_KEY is set, else deterministic stub.
- Evidence: real Elastic MCP when ELASTIC_MCP_URL is set, else seeded stub.

This lets the contract-enforced golden path run end-to-end offline.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

# Read a local .env (if present) into os.environ. No-op when the file is absent,
# so production env vars still win.
load_dotenv()


def _int(name: str, default: int) -> int:
    # Treat empty string (a blank line in .env.example) the same as unset.
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


class Settings(BaseModel):
    # --- LLM ---
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"  # plain model string ADK accepts

    # --- Evidence (Elastic via MCP) ---
    elastic_mcp_url: str | None = None
    elastic_mcp_transport: str = "streamable_http"

    # --- Reflection export (Phoenix/Arize) ---
    phoenix_endpoint: str | None = None
    phoenix_project: str = "launchpilot-agent"

    # --- Server ---
    port: int = 8000

    # --- Signal thresholds (UNVERIFIED placeholders, agent-tool-spec §6) ---
    signal_threshold_high: float = 2.0  # >= this lift => strong signal
    signal_threshold_low: float = 1.3   # >= this => weak signal; below => noise

    # --- Failure policy (agent-tool-spec §4) ---
    tool_max_retries: int = 2   # Class 1: cheap retries, no LLM
    backtrack_limit: int = 3    # Class 2: max review-fail re-runs before FAILED

    @property
    def use_real_llm(self) -> bool:
        # Presence of an API key is the single switch between ADK and stub workers.
        return bool(self.gemini_api_key)

    @property
    def use_real_elastic(self) -> bool:
        # Presence of an MCP URL is the single switch between live Elastic and seed.
        return bool(self.elastic_mcp_url)


@lru_cache
def get_settings() -> Settings:
    # Cached so every module reads one immutable Settings instance per process.
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-2.0-flash",
        elastic_mcp_url=os.environ.get("ELASTIC_MCP_URL") or None,
        elastic_mcp_transport=os.environ.get("ELASTIC_MCP_TRANSPORT") or "streamable_http",
        phoenix_endpoint=os.environ.get("PHOENIX_COLLECTOR_ENDPOINT") or None,
        phoenix_project=os.environ.get("PHOENIX_PROJECT_NAME") or "launchpilot-agent",
        port=_int("PORT", 8000),
        signal_threshold_high=_float("SIGNAL_THRESHOLD_HIGH", 2.0),
        signal_threshold_low=_float("SIGNAL_THRESHOLD_LOW", 1.3),
        tool_max_retries=_int("TOOL_MAX_RETRIES", 2),
        backtrack_limit=_int("BACKTRACK_LIMIT", 3),
    )
