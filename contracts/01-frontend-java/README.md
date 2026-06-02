# LaunchPilot Frontend-Backend Contract

Status: Draft v0.4  
Source: Gemini first-pass contract plus confirmed C1/C2/C3 diagrams and main user scenario  
Last updated: 2026-06-02

## Contract Principles

This contract is for the boundary between the Next.js frontend and Java Spring Boot business backend.

The frontend only talks to the Java backend. It never calls Python Agent Service, Gemini, Elastic, or Arize directly.

Core runtime rules:

- Analysis is asynchronous. `POST /api/agent/run` returns `202 Accepted` immediately.
- This directory has two contract specs:
  - `openapi.yaml`: REST surface for CSV import, run start, coarse run snapshot, and approve/cancel fallback.
  - `asyncapi.yaml`: active WebSocket runtime for live conversation, persisted timeline events, approval gates, cancel, reconnect resume, and missed-event replay.
- The accepted REST response includes `stream_url`. The frontend opens that WebSocket URL and then follows `asyncapi.yaml`.
- Agent conversation lines and agent runtime timeline events are loss-intolerant. They must be delivered, resumed, and replayed through WebSocket using persisted `sequence` values.
- `GET /api/agent/runs/{agent_run_id}` remains a coarse snapshot and polling fallback for status/result visibility. It is not the source of truth for reconstructing the user-visible conversation timeline.
- Candidate signals, hypotheses, and experiment plans are temporary before human approval. The frontend may edit them in React state, but the backend must not persist final calendar or brief documents before approval.
- Approval is append-only. `approval.approve` over WebSocket is the primary approval command; `POST /api/agent/actions/{agent_run_id}/approve` remains the REST fallback. Approval creates new `calendar_events` and `growth_briefs` documents in Elastic.
- Cancel is an intervention command. `run.cancel` over WebSocket is primary; `POST /api/agent/actions/{agent_run_id}/cancel` is the REST fallback.
- Streamed reasoning must be glass-box, not raw private chain-of-thought. The backend sends user-visible observations, tool summaries, evidence references, and structured artifacts.
- Response payloads use `snake_case` to match the Java Gateway and Python Agent contract.
- Timestamps are ISO 8601 strings with timezone offsets, for example `2026-06-01T16:31:00+09:00`.

## Endpoint Summary

| Flow | Method | Path | Owner |
| --- | --- | --- | --- |
| CSV ingestion | `POST` | `/api/import/csv` | Java `ImportController` |
| Run async agent | `POST` | `/api/agent/run` | Java `AgentController` |
| Observe/intervene in run | `WS` | `/api/agent/runs/{agent_run_id}/stream` | Java `AgentController`; see `asyncapi.yaml` |
| Coarse run/result snapshot | `GET` | `/api/agent/runs/{agent_run_id}` | Java `AgentController` |
| Approve plan fallback | `POST` | `/api/agent/actions/{agent_run_id}/approve` | Java `BusinessController` |
| Cancel run fallback | `POST` | `/api/agent/actions/{agent_run_id}/cancel` | Java `AgentController` |

`POST /api/calendar/events` from the sequence diagram is treated as the lower-level business action behind approval. The frontend should use the approval endpoint above so the approved brief and calendar events are committed as one append-only operation.

## 1. CSV Ingestion

`POST /api/import/csv`

Purpose: upload SNS metric CSV data and index normalized rows into Elastic with refresh enabled.

Request content type: `multipart/form-data`

Fields:

- `file`: CSV file. Required.
- `workspace_id`: Workspace key. Required.
- `campaign_id`: Campaign key. Required.
- `source_platform`: Optional source platform. Default: `unknown`.

Response: `201 Created`

```json
{
  "ok": true,
  "import_id": "imp_20260601_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "indexed_count": 184,
  "failed_count": 0,
  "columns": ["post_id", "published_at", "channel", "views", "likes", "comments", "save_rate"],
  "created_at": "2026-06-01T16:30:10+09:00"
}
```

## 2. Async Agent Run

`POST /api/agent/run`

Purpose: trigger the Python Agent Service through the Java gateway without occupying the Tomcat request thread.

Request:

```json
{
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "question": "What should we test next week?",
  "date_range": {
    "start": "2026-05-25",
    "end": "2026-06-01"
  },
  "parent_brief_id": null
}
```

Fields:

- `workspace_id`: Required workspace scope.
- `campaign_id`: Required campaign scope.
- `question`: Required user intent.
- `date_range`: Required analysis window.
- `parent_brief_id`: Optional growth brief ID for restoring continuity in a new session.

Response: `202 Accepted`

```json
{
  "ok": true,
  "agent_run_id": "run_20260601_001",
  "status": "PENDING",
  "stream_url": "/api/agent/runs/run_20260601_001/stream",
  "next_poll_url": "/api/agent/runs/run_20260601_001",
  "created_at": "2026-06-01T16:31:00+09:00"
}
```

## 3. Active Agent Runtime

`WS /api/agent/runs/{agent_run_id}/stream`

Purpose: provide the live, persisted agent conversation and runtime timeline for the Campaign Agent Workspace.

The WebSocket runtime is specified in `asyncapi.yaml`, not `openapi.yaml`.

It supports two interaction modes:

- Observational HOTL: the user watches step updates, tool summaries, evidence observations, signals, hypotheses, and drafted plans.
- Approval-based HITL: the backend pauses before consequential business writes, then waits for approve, reject, payload edit, or cancel commands.

Server-to-client event types:

```text
connection.resume_accepted
connection.replay_started
connection.replay_completed
connection.full_sync_required
connection.reauth_required
connection.session_expired
run.started
step.updated
user.message.created
assistant.message.created
document.created
observation.created
tool.updated
signal.detected
hypothesis.created
experiment_plan.drafted
approval.requested
approval.committed
run.paused
run.resumed
run.cancelled
run.completed
run.failed
```

Client-to-server command types:

```text
connection.resume
connection.full_sync
run.cancel
approval.update_payload
approval.approve
approval.reject
```

Examples live beside both specs:

- `examples/agent-stream-user-message-created-event.json`
- `examples/agent-stream-run-started-event.json`
- `examples/agent-stream-document-created-event.json`
- `examples/agent-stream-resume-command.json`
- `examples/agent-stream-resume-accepted-event.json`
- `examples/agent-stream-full-sync-required-event.json`
- `examples/agent-stream-full-sync-command.json`
- `examples/agent-stream-observation-created-event.json`
- `examples/agent-stream-approval-requested-event.json`
- `examples/agent-stream-approval-committed-event.json`
- `examples/agent-stream-approval-approve-command.json`
- `examples/agent-stream-cancel-command.json`

The frontend should map stream events like this:

- Every persisted timeline event has a monotonic per-run `sequence`. The frontend stores the last fully applied `sequence`.
- After reconnecting, the frontend sends `connection.resume` with `last_received_sequence`.
- The backend replays all missed persisted timeline events in sequence order. If incremental replay is unavailable, the backend sends `connection.full_sync_required`; the frontend then sends `connection.full_sync`, and the backend replays the full persisted timeline over WebSocket.
- `step.updated` updates the fixed agent run status area.
- `user.message.created` and `assistant.message.created` append direct conversation bubbles.
- `document.created` appends a clickable document card in the conversation timeline. The frontend opens the card in the right-side inspector and renders `document.content` as markdown.
- `observation.created`, `signal.detected`, `hypothesis.created`, and `experiment_plan.drafted` append visible workspace timeline messages.
- `approval.requested` opens the review surface with editable draft payload.
- `approval.committed` carries `growth_brief_id` and `created_calendar_events` after the approved plan is persisted. The frontend uses this event, not the coarse snapshot, to route to the created brief or calendar artifacts on the WebSocket primary path.
- `run.cancelled`, `run.completed`, and `run.failed` close the active run lifecycle.
- Client commands that mutate server state use `command_id` as an idempotency key. The server must execute the same `command_id` at most once and return the previously accepted outcome on duplicate delivery.

## 4. Snapshot Agent Run And Result

`GET /api/agent/runs/{agent_run_id}`

Purpose: provide coarse runtime status and completed structured result when the stream is unavailable or the page needs a status refresh. This endpoint must not be used to reconstruct missing conversation lines; missing lines are recovered through the WebSocket replay protocol in `asyncapi.yaml`.

Runtime status enum:

```text
PENDING
RUNNING_SIGNAL_DETECTION
RUNNING_EVIDENCE_SEARCH
RUNNING_HYPOTHESIS_GENERATION
RUNNING_EXPERIMENT_GENERATION
WAITING_FOR_APPROVAL
SUCCESS
FAILED
```

`WAITING_FOR_APPROVAL` means the frontend can render the review surface and allow edits. `SUCCESS` means the final human approval has already been processed.

Response while running:

```json
{
  "agent_run_id": "run_20260601_001",
  "status": "RUNNING_EVIDENCE_SEARCH",
  "current_stage": "SEARCHING_EVIDENCE",
  "retry_count": 0,
  "error_message": null,
  "payload": null,
  "tool_call_logs": [
    {
      "sequence": 1,
      "tool_name": "query_metric_baseline",
      "status": "SUCCESS",
      "duration_ms": 142
    }
  ]
}
```

Response when ready for approval:

```json
{
  "agent_run_id": "run_20260601_001",
  "status": "WAITING_FOR_APPROVAL",
  "current_stage": "VALIDATING",
  "retry_count": 0,
  "error_message": null,
  "payload": {
    "signals": [
      {
        "id": "sig_001",
        "type": "content_outperformance",
        "title": "BTS shorts outperformed recent baseline",
        "description": "Two behind-the-scenes TikTok shorts showed save rates 2.8x above the 30-day channel baseline.",
        "metric_name": "save_rate",
        "current_value": 0.074,
        "baseline_value": 0.026,
        "lift_ratio": 2.8,
        "date_window": {
          "start": "2026-05-25",
          "end": "2026-06-01"
        },
        "confidence": "high",
        "evidence_refs": ["post_014", "post_017", "note_006"]
      }
    ],
    "hypotheses": [
      {
        "id": "hyp_001",
        "signal_ids": ["sig_001"],
        "statement": "Raw behind-the-scenes clips may be converting passive viewers into deeper engagement better than polished teaser assets.",
        "rationale": "The strongest posts share the BTS angle and face-first hook, and team notes mention strong fan reaction to raw practice footage.",
        "confidence": "medium_high",
        "supporting_evidence_refs": ["post_014", "post_017", "note_006"],
        "caveats": ["External fan community activity was not measured.", "This is a correlation, not a causal claim."]
      }
    ],
    "experiment_plan": {
      "id": "plan_001",
      "summary": "This week's strongest signal is repeated overperformance from BTS short-form clips. Next week should test whether the same raw format can reproduce engagement uplift across TikTok and Instagram.",
      "overall_confidence": "medium_high",
      "items": [
        {
          "id": "exp_001",
          "hypothesis_id": "hyp_001",
          "title": "BTS face-first hook test",
          "channel": "tiktok",
          "content_format": "12-second short",
          "hook": "Open with a close-up reaction in the first 2 seconds.",
          "cta": "Ask fans to comment which practice moment they want next.",
          "target_metric": "save_rate",
          "success_criteria": "save_rate >= 1.5x TikTok 30-day baseline within 48 hours",
          "scheduled_at": "2026-06-03T20:00:00+09:00",
          "production_brief": "Use raw rehearsal footage, minimal polish, subtitles on-screen."
        }
      ]
    }
  },
  "tool_call_logs": [
    {
      "sequence": 1,
      "tool_name": "query_metric_baseline",
      "status": "SUCCESS",
      "duration_ms": 142
    },
    {
      "sequence": 2,
      "tool_name": "search_team_notes",
      "status": "SUCCESS",
      "duration_ms": 310
    }
  ]
}
```

Response when failed:

```json
{
  "agent_run_id": "run_20260601_001",
  "status": "FAILED",
  "current_stage": "VALIDATING",
  "retry_count": 2,
  "error_message": "Experiment plan schema validation failed after retry.",
  "payload": null,
  "tool_call_logs": []
}
```

## 5. Approve Experiment Plan

`POST /api/agent/actions/{agent_run_id}/approve`

Purpose: REST fallback to commit the user's final selected and edited experiments as immutable Elastic documents.

The frontend sends the final experiments from React state. These may differ from the original candidate items returned by stream or the coarse snapshot.

Request:

```json
{
  "experiment_plan_id": "plan_001",
  "approved_by": "demo_user",
  "final_experiments": [
    {
      "id": "exp_001",
      "hypothesis_id": "hyp_001",
      "title": "BTS face-first hook test (edited)",
      "channel": "tiktok",
      "content_format": "12-second short",
      "hook": "Open with a close-up reaction in the first 2 seconds.",
      "cta": "Ask fans to comment which practice moment they want next.",
      "target_metric": "save_rate",
      "success_criteria": "save_rate >= 1.5x TikTok 30-day baseline within 48 hours",
      "scheduled_at": "2026-06-03T20:00:00+09:00",
      "production_brief": "Use raw rehearsal footage, minimal polish, subtitles on-screen."
    }
  ]
}
```

Response: `200 OK`

```json
{
  "ok": true,
  "message": "Human approval processed successfully.",
  "growth_brief_id": "brief_20260601_001",
  "created_calendar_events": [
    {
      "event_id": "cal_101",
      "title": "BTS face-first hook test (edited)",
      "scheduled_at": "2026-06-03T20:00:00+09:00"
    }
  ],
  "persisted_at": "2026-06-01T16:33:15+09:00"
}
```

## Shared Schemas

### Confidence

Allowed values:

- `low`
- `medium`
- `medium_high`
- `high`

### Tool Call Log

Tool call logs are UI-observable traces for the workroom timeline. They are not the source of truth for Arize telemetry.

Allowed tool statuses:

- `PENDING`
- `RUNNING`
- `SUCCESS`
- `FAILED`

### Frontend Memory Rule

Before approval, the frontend owns user edits:

- selected experiment cards,
- edited titles,
- edited hooks,
- edited CTA text,
- edited production briefs.

The backend owns only run status, original generated payload, and final append-only persistence.

## Open Decisions

- Authentication is not included in this hackathon contract.
- CSV required column validation should be finalized when sample CSV files are fixed.
- Polling interval recommendation is 1.5 seconds, but the backend contract does not enforce it.
- The frontend may immediately route to the calendar view with local state after approval to avoid Elastic refresh latency.
