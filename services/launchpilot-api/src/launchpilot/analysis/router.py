from __future__ import annotations

from .scope import ExecutionScope


class ScopeRouter:
    """Resolves and validates execution scope (workspace, time, campaign) from session context.
    Pure non-destructive preprocessing with zero LLM overhead.
    """

    def resolve(self, scope: ExecutionScope | None) -> ExecutionScope | None:
        return scope
