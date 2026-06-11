"""ADR-005 Phase 2-4: episode build, persistence/retrieval, checkpoint, restore."""
from __future__ import annotations

from types import SimpleNamespace

from app.orchestration.checkpoint import Checkpointer
from app.orchestration.models import TurnOutcome
from app.runtime.episode import EpisodeOutcome, build_episode
from app.runtime.episode_query import recent_episode_context
from app.runtime.repository import InMemoryAgentRuntimeRepository, RuntimeArtifact
from app.runtime.restore import restore_from_episode
from app.runtime.state import (
    DeltaIntent,
    PhaseType,
    ScopeContext,
    SharedStateVector,
    StateDeltaProposal,
)


def _state(phase: PhaseType = PhaseType.HYPOTHESIS_GEN, revision: int = 3) -> SharedStateVector:
    return SharedStateVector(
        scope=ScopeContext(workspace_id="demo_workspace", campaign_id="camp_1", thread_id="thread_x"),
        current_phase=phase,
        target_phase=phase,
        revision=revision,
        active_run_id="run_1",
    )


# --- build_episode ---------------------------------------------------------

def test_build_episode_carries_scope_outcome_and_snapshot() -> None:
    state = _state()
    state.active_chat_history = [{"role": "user", "content": "threshold 1.3"}]
    ep = build_episode(state, EpisodeOutcome.BACKTRACK, state.active_chat_history, {"metric": "save_rate"})
    assert ep.workspace_id == "demo_workspace" and ep.campaign_id == "camp_1"
    assert ep.outcome == EpisodeOutcome.BACKTRACK and ep.run_id == "run_1"
    assert ep.state_snapshot.revision == 3 and ep.state_snapshot.key_params == {"metric": "save_rate"}
    assert ep.summary is None and ep.embedding is None  # MVP deferred
    # raw is copied, not aliased
    state.active_chat_history.append({"role": "user", "content": "more"})
    assert len(ep.raw) == 1


# --- repository episode ops ------------------------------------------------

async def test_repository_episode_save_query_filter_and_recency() -> None:
    repo = InMemoryAgentRuntimeRepository()
    scope = _state().scope
    for i, outcome in enumerate([EpisodeOutcome.FORWARD, EpisodeOutcome.BACKTRACK, EpisodeOutcome.FORWARD]):
        ep = build_episode(_state(PhaseType.DATA_ANALYSIS, revision=i), outcome, [])
        ep.created_at = float(i)  # deterministic recency
        await repo.save_episode(ep)

    all_da = await repo.query_episodes(scope, phase=PhaseType.DATA_ANALYSIS.value)
    assert [e.state_snapshot.revision for e in all_da] == [2, 1, 0]  # recency desc

    backtracks = await repo.query_episodes(scope, outcome=EpisodeOutcome.BACKTRACK)
    assert len(backtracks) == 1 and backtracks[0].outcome == EpisodeOutcome.BACKTRACK

    limited = await repo.query_episodes(scope, limit=2)
    assert len(limited) == 2


async def test_repository_episode_scope_isolation_and_get() -> None:
    repo = InMemoryAgentRuntimeRepository()
    ep = build_episode(_state(), EpisodeOutcome.FORWARD, [])
    await repo.save_episode(ep)
    other_scope = ScopeContext(workspace_id="demo_workspace", campaign_id="other", thread_id="t")
    assert await repo.query_episodes(other_scope) == []
    assert (await repo.get_episode(ep.episode_id)).episode_id == ep.episode_id
    assert await repo.get_episode("missing") is None


# --- checkpoint outcome classification ------------------------------------

def _decision(intent: DeltaIntent):
    return SimpleNamespace(delta=StateDeltaProposal(intent=intent))


def test_checkpointer_outcome_classification() -> None:
    cp = Checkpointer(emitter=None)  # _outcome_for does not touch the emitter
    forward = TurnOutcome({"phase": "DATA_ANALYSIS", "signals": 3})
    assert cp._outcome_for(_decision(DeltaIntent.BACKTRACK), forward) == EpisodeOutcome.BACKTRACK
    assert cp._outcome_for(_decision(DeltaIntent.APPROVE), forward) == EpisodeOutcome.APPROVE
    assert cp._outcome_for(_decision(DeltaIntent.REJECT), forward) == EpisodeOutcome.REJECT
    assert cp._outcome_for(_decision(DeltaIntent.START_ANALYSIS), forward) == EpisodeOutcome.FORWARD
    assert cp._outcome_for(_decision(DeltaIntent.CHAT), TurnOutcome({"mode": "direct"})) is None


def test_phase_round_completed_guards() -> None:
    assert Checkpointer._phase_round_completed(TurnOutcome({"phase": "X", "signals": 1})) is True
    assert Checkpointer._phase_round_completed(TurnOutcome({"phase": "X", "status": "missing"})) is False
    assert Checkpointer._phase_round_completed(TurnOutcome({"phase": "X", "validator_passed": False})) is False
    assert Checkpointer._phase_round_completed(TurnOutcome({"mode": "direct"})) is False


# --- retrieval context (Phase 3) ------------------------------------------

async def test_recent_episode_context_compact_and_none() -> None:
    repo = InMemoryAgentRuntimeRepository()
    scope = _state().scope
    assert await recent_episode_context(repo, scope, PhaseType.DATA_ANALYSIS) is None
    ep = build_episode(_state(PhaseType.DATA_ANALYSIS), EpisodeOutcome.BACKTRACK, [], {"metric": "save_rate"})
    await repo.save_episode(ep)
    ctx = await recent_episode_context(repo, scope, PhaseType.DATA_ANALYSIS)
    assert ctx is not None and "[past_episodes]" in ctx and "backtrack" in ctx and "save_rate" in ctx
    assert await recent_episode_context(repo, None, PhaseType.DATA_ANALYSIS) is None


# --- restore (Phase 4) -----------------------------------------------------

async def test_restore_rebuilds_state_and_artifacts_from_snapshot() -> None:
    repo = InMemoryAgentRuntimeRepository()
    scope = _state().scope
    # A plan artifact persisted earlier, referenced by the episode snapshot.
    artifact = RuntimeArtifact(
        artifact_type="experiment_plan",
        phase=PhaseType.EXPERIMENT_PLAN.value,
        payload={"experiment_plan": {"id": "plan_42", "summary": "s"}},
    )
    ref = await repo.save_runtime_artifact(scope, artifact)

    snap_state = _state(PhaseType.EXPERIMENT_PLAN, revision=7)
    snap_state.phase_artifact_refs[PhaseType.EXPERIMENT_PLAN.value] = [ref]
    episode = build_episode(snap_state, EpisodeOutcome.FORWARD, [], {"metric": "shares"})
    await repo.save_episode(episode)

    # A live state that has drifted forward; restore should rewind it.
    live = _state(PhaseType.EXPERIMENT_EVAL, revision=12)
    await restore_from_episode(live, episode, repo)

    assert live.current_phase == PhaseType.EXPERIMENT_PLAN
    assert live.revision == 12  # NOT rolled back (monotonic, preserves OCC)
    assert live.phase_artifacts[PhaseType.EXPERIMENT_PLAN.value]["experiment_plan"]["id"] == "plan_42"
    assert live.active_artifact_id == "plan_42"
    assert any("Restored to" in lesson.summary for lesson in live.compact_lessons)
