"""Episode retrieval for prompt context (ADR-005, Phase 3).

MVP (C6): hard filter (workspace + campaign + phase) + recency, compact text
injection only. No LLM summary, no embedding kNN yet. We deliberately do NOT
dump raw spans into the prompt (C3 bloat guard); past episodes are rendered as
short outcome + key-param lines, and raw drill-down stays an explicit lookup.
"""
from __future__ import annotations

from app.runtime.repository import AgentRuntimeRepository
from app.runtime.state import PhaseType, ScopeContext


async def recent_episode_context(
    repository: AgentRuntimeRepository,
    scope: ScopeContext | None,
    phase: PhaseType,
    *,
    limit: int = 3,
) -> str | None:
    """Return a compact, prompt-safe summary of recent episodes for a phase."""
    if scope is None:
        return None
    episodes = await repository.query_episodes(scope, phase=phase.value, limit=limit)
    if not episodes:
        return None
    lines = []
    for ep in episodes:
        params = ", ".join(f"{k}={v}" for k, v in ep.state_snapshot.key_params.items())
        suffix = f" ({params})" if params else ""
        lines.append(f"- [{ep.outcome.value}] rev{ep.state_snapshot.revision}{suffix}")
    return "[past_episodes]\n" + "\n".join(lines)
