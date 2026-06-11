# LaunchPilot Agent Runtime Elastic Contract

Status: Draft v0.1  
Boundary: Python Agent Core <-> ElasticSearch Runtime Repository  
Last updated: 2026-06-11

## Purpose

This contract defines runtime-only Elastic documents used by the Python Agent Core
to coordinate state-reactive orchestration across process restarts and scale-out.
It also defines the campaign-scoped conversation memory the Python Agent Core
may read to recover session context.

This is **not** the Java business persistence contract. Business documents remain
owned by `contracts/03-java-elastic`:

- `content_posts`
- `growth_briefs`
- `calendar_events`

The runtime indices below are internal coordination records. They must not be
treated as approved business artifacts, continuity evidence, or customer-facing
source of truth.

## Index Summary

| Index | Writer | Reader | Mutability | Purpose |
|---|---|---|---|---|
| `agent_thread_states` | Python Agent Core | Python Agent Core | Mutable with revision/OCC | Latest `SharedStateVector` snapshot for one thread. |
| `agent_state_deltas` | Python Agent Core | Python Agent Core, observability tooling | Append-only | Auditable transition event log produced from free-form turns. |
| `agent_runtime_artifacts` | Python Agent Core | Python Agent Core | Append-only versioned, TTL | Pre-approval runtime artifact snapshots or refs. |
| `agent_thread_messages` | Java Backend | Python Agent Core, Java Backend | Append-only | Session conversation memory and replay source scoped by workspace + campaign + thread. |

## Core Invariants

- Runtime documents are not business documents.
- Runtime documents may exist before human approval, but they are TTL-bound and
  excluded from `growth_briefs`, `calendar_events`, and evidence search.
- Only Java may write approved `growth_briefs` and `calendar_events`.
- Python may write only runtime coordination indices defined by this contract:
  `agent_thread_states`, `agent_state_deltas`, and `agent_runtime_artifacts`.
- Every runtime document must include `thread_id`, `workspace_id`, and
  `campaign_id`. State and delta documents must include revision fields.
  TTL-managed documents must include `created_at` and `expires_at`.
- `workspace_id` is the tenant/data boundary. In the no-login MVP it may use a
  default namespace such as `demo_workspace`, but runtime queries must still
  include it.
- `campaign_id` is the primary working context for the user experience and
  Agent Core prompt setup. It must be combined with `workspace_id`, not used as
  the sole isolation key.
- `agent_state_deltas` is append-only. Do not update delta events in place.
- `agent_thread_messages` is append-only. Message correction creates a new
  message or redaction marker; it does not update the original message in place.
- `agent_thread_states.revision` is monotonic per `thread_id`.
- State commits must use optimistic concurrency control. Stale writes must fail
  and be retried or surfaced as `AGENT_BUSY`.

## Index: `agent_thread_states`

Purpose: authoritative latest runtime state for a conversation thread.

Document ID recommendation: `thread_id`.

Required fields:

- `thread_id`
- `workspace_id`
- `campaign_id`
- `current_phase`
- `target_phase`
- `user_intent`
- `revision`
- `active_run_id`
- `active_artifact_id`
- `pending_approval_id`
- `compact_lessons`
- `phase_artifact_refs`
- `active_chat_history`
- `updated_at`
- `expires_at`

Allowed `current_phase` / `target_phase`:

- `DATA_ANALYSIS`
- `HYPOTHESIS_GEN`
- `EXPERIMENT_PLAN`
- `EXPERIMENT_EVAL`

Allowed `user_intent`:

- `INITIAL_RUN`
- `FREE_CHAT`
- `BACKTRACK`
- `ARTIFACT_REVISION`
- `APPROVE`

`phase_artifact_refs` should contain refs to `agent_runtime_artifacts`, not large
payloads, once artifacts become large.

Example:

```json
{
  "thread_id": "thread_20260611_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "current_phase": "EXPERIMENT_PLAN",
  "target_phase": "EXPERIMENT_PLAN",
  "user_intent": "FREE_CHAT",
  "revision": 8,
  "active_run_id": null,
  "active_artifact_id": "art_thread_20260611_001_plan_v2",
  "pending_approval_id": "appr_abc",
  "compact_lessons": [
    {
      "phase": "DATA_ANALYSIS",
      "summary": "Backtrack requested for DATA_ANALYSIS; changed metric=save_rate, threshold_lift=2.0",
      "timestamp": 1781090400.0
    }
  ],
  "phase_artifact_refs": {
    "DATA_ANALYSIS": ["art_thread_20260611_001_signals_v2"],
    "HYPOTHESIS_GEN": ["art_thread_20260611_001_hypotheses_v2"],
    "EXPERIMENT_PLAN": ["art_thread_20260611_001_plan_v2"],
    "EXPERIMENT_EVAL": []
  },
  "active_chat_history": [
    {"role": "user", "content": "이 실험 제목을 더 짧게 바꿔줘."}
  ],
  "updated_at": "2026-06-11T06:00:00Z",
  "expires_at": "2026-06-12T06:00:00Z"
}
```

## Index: `agent_thread_messages`

Purpose: conversation memory for Agent Core, scoped by
`workspace_id + campaign_id + thread_id`. This allows Python to recover useful
session history from Elastic instead of relying only on process memory or UI
state.

Document ID recommendation:

`msg_{thread_id}_{sequence}` or Java-generated `message_id`.

Required fields:

- `message_id`
- `thread_id`
- `campaign_id`
- `workspace_id`
- `sequence`
- `role`
- `content`
- `blocks_summary`
- `artifact_refs`
- `delta_id`
- `created_at`

Allowed `role`:

- `user`
- `assistant`
- `system`

Rules:

- Java writes user messages because Java receives frontend `message.send` first
  and owns the public thread timeline.
- Default ownership: Java also persists assistant/system message summaries after
  receiving Python stream messages. Python treats this index as a read-only
  memory source. If a later deployment changes this owner, it must do so
  explicitly to avoid duplicate assistant messages.
- `content` is the user-visible text, not chain-of-thought, raw Gemini chunks,
  raw MCP frames, private prompts, or credentials.
- `blocks_summary` is a compact user-safe summary of emitted blocks. Large
  artifacts should be referenced through `artifact_refs`.
- Python prompt assembly should read bounded recent messages by
  `workspace_id + campaign_id + thread_id`, then summarize/prune before LLM
  calls.

Example:

```json
{
  "message_id": "msg_thread_20260611_001_0004",
  "thread_id": "thread_20260611_001",
  "campaign_id": "camp_comeback_teaser",
  "workspace_id": "demo_workspace",
  "sequence": 4,
  "role": "user",
  "content": "실험 제목을 더 짧게, BTS hook 중심으로 바꿔줘.",
  "blocks_summary": [],
  "artifact_refs": ["art_thread_20260611_001_plan_v2"],
  "delta_id": "delta_thread_20260611_001_0009",
  "created_at": "2026-06-11T06:01:00Z"
}
```

## Index: `agent_state_deltas`

Purpose: append-only audit log of conversation-derived state transition proposals
and reducer decisions.

Document ID recommendation:

`delta_{thread_id}_{revision_after}`

Required fields:

- `delta_id`
- `thread_id`
- `workspace_id`
- `campaign_id`
- `revision_before`
- `revision_after`
- `source`
- `intent`
- `response_mode`
- `target_phase`
- `mutation`
- `referenced_artifact_ids`
- `confidence`
- `requires_confirmation`
- `reducer_decision`
- `created_at`

Allowed `source`:

- `turn_interpreter`
- `phase_agent_escalation`
- `system`

Allowed `response_mode`:

- `direct`
- `delegate`
- `rerun`
- `clarify`

Allowed `reducer_decision`:

- `accepted`
- `rejected`
- `downgraded_to_clarify`
- `busy`
- `conflict`

Example:

```json
{
  "delta_id": "delta_thread_20260611_001_0009",
  "thread_id": "thread_20260611_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "revision_before": 8,
  "revision_after": 9,
  "source": "turn_interpreter",
  "intent": "backtrack",
  "response_mode": "rerun",
  "target_phase": "DATA_ANALYSIS",
  "mutation": {"metric": "shares"},
  "referenced_artifact_ids": [],
  "confidence": 0.87,
  "requires_confirmation": false,
  "reducer_decision": "accepted",
  "created_at": "2026-06-11T06:01:00Z"
}
```

## Index: `agent_runtime_artifacts`

Purpose: runtime-only pre-approval artifact snapshot or ref.

Document ID recommendation: `artifact_id`.

Required fields:

- `artifact_id`
- `thread_id`
- `workspace_id`
- `campaign_id`
- `phase`
- `artifact_kind`
- `revision`
- `payload`
- `payload_ref`
- `created_at`
- `expires_at`
- `runtime_only`

Rules:

- `runtime_only` must be `true`.
- Exactly one of `payload` or `payload_ref` should be populated for large
  artifacts.
- Approved copies must be written by Java into `growth_briefs` and
  `calendar_events`; Python runtime artifacts are not approval records.

Allowed `artifact_kind`:

- `signals`
- `hypotheses`
- `experiment_plan`
- `evaluation`
- `generic`

## Concurrency Rules

Elastic commits must use optimistic concurrency control:

- Load state with `_seq_no`, `_primary_term`, and `revision`.
- Build a new state and delta event against that revision.
- Commit only if the stored document still has the expected revision / sequence.
- On conflict, reload and re-evaluate or return `AGENT_BUSY`.

Do not use update-by-query for state commits.

## Retention

Recommended MVP retention:

- `agent_thread_states`: 24 hours after last update.
- `agent_runtime_artifacts`: 24 hours after last update.
- `agent_state_deltas`: 7 days for debugging and Phoenix correlation.
- `agent_thread_messages`: 7 days or demo reset boundary. Longer retention
  requires explicit privacy/product decision.

Retention may be shortened for demo deployments.

## Contract Relationship

This contract amends prior wording that said "pre-approval candidates are never
stored" as follows:

Pre-approval candidates are never stored as business documents. They may be
stored as runtime-only Elastic documents with TTL for scale-out coordination,
resume, and debugging.
