"""Restore from an episode checkpoint (ADR-005, Phase 4).

 rewind is two layers: state mutation (here, on the Redis-backed working copy)
and the audit record (a backtrack episode). Restore rebuilds the live state from
a past episode's `state_snapshot` and re-hydrates phase artifact payloads from
their runtime-artifact refs. lessons alone cannot do this (lossy), which is why
each episode carries a snapshot (Risk 3).

`revision` is intentionally NOT rolled back to the snapshot value: the restore is
a new forward transition (monotonic revision preserves OCC). A compact lesson
records that a restore happened.
"""
from __future__ import annotations

from app.runtime.episode import Episode
from app.runtime.repository import AgentRuntimeRepository
from app.runtime.state import CompactLesson, IntentType, SharedStateVector


async def restore_from_episode(
    state: SharedStateVector,
    episode: Episode,
    repository: AgentRuntimeRepository,
) -> SharedStateVector:
    snap = episode.state_snapshot
    state.current_phase = snap.current_phase
    state.target_phase = snap.target_phase
    state.user_intent = IntentType.BACKTRACK
    state.phase_artifact_refs = {k: list(v) for k, v in snap.phase_artifact_refs.items()}

    # Rehydrate phase artifact payloads from their runtime-artifact refs so the
    # downstream phases see the restored artifacts, not stale or empty ones.
    rebuilt: dict[str, dict] = {phase: {} for phase in state.phase_artifacts}
    for phase_value, refs in state.phase_artifact_refs.items():
        artifacts = await repository.load_runtime_artifacts(refs)
        merged: dict = {}
        for artifact in artifacts:
            merged.update(artifact.payload)
        rebuilt[phase_value] = merged
    state.phase_artifacts = rebuilt
    state.active_artifact_id = (
        rebuilt.get(snap.current_phase.value, {}).get("experiment_plan", {}).get("id")
        if isinstance(rebuilt.get(snap.current_phase.value, {}).get("experiment_plan"), dict)
        else None
    )

    params = ", ".join(f"{k}={v}" for k, v in snap.key_params.items())
    summary = f"Restored to {snap.current_phase.value} (episode {episode.episode_id}, rev{snap.revision})"
    if params:
        summary += f"; {params}"
    state.compact_lessons.append(CompactLesson(phase=snap.current_phase, summary=summary[:280]))
    state.compact_lessons = state.compact_lessons[-6:]
    return state
