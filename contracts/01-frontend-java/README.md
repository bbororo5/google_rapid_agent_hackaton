# LaunchPilot Frontend-Backend Contract

Status: Draft v0.2  
Source: Gemini first-pass contract plus confirmed C1/C2/C3 diagrams and main user scenario  
Last updated: 2026-06-01

## Contract Principles

This contract is for the boundary between the Next.js frontend and Java Spring Boot business backend.

The frontend only talks to the Java backend. It never calls Python Agent Service, Gemini, Elastic, or Arize directly.

Core runtime rules:

- Analysis is asynchronous. `POST /api/agent/run` returns `202 Accepted` immediately.
- The frontend polls `GET /api/agent/runs/{agent_run_id}` until the run reaches `WAITING_FOR_APPROVAL`, `SUCCESS`, or `FAILED`.
- Candidate signals, hypotheses, and experiment plans are temporary before human approval. The frontend may edit them in React state, but the backend must not persist final calendar or brief documents before approval.
- Approval is append-only. `POST /api/agent/actions/{agent_run_id}/approve` creates new `calendar_events` and `growth_briefs` documents in Elastic.
- Response payloads use `snake_case` to match the Java Gateway and Python Agent contract.
- Timestamps are ISO 8601 strings with timezone offsets, for example `2026-06-01T16:31:00+09:00`.

## Endpoint Summary

| Flow | Method | Path | Owner |
| --- | --- | --- | --- |
| CSV ingestion | `POST` | `/api/import/csv` | Java `ImportController` |
| Run async agent | `POST` | `/api/agent/run` | Java `AgentController` |
| Poll run/result | `GET` | `/api/agent/runs/{agent_run_id}` | Java `AgentController` |
| Approve plan | `POST` | `/api/agent/actions/{agent_run_id}/approve` | Java `BusinessController` |

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
  "next_poll_url": "/api/agent/runs/run_20260601_001",
  "created_at": "2026-06-01T16:31:00+09:00"
}
```

## 3. Poll Agent Run And Result

`GET /api/agent/runs/{agent_run_id}`

Purpose: provide both runtime status and completed structured result in a single polling contract.

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

`WAITING_FOR_APPROVAL` means the frontend can render the three-panel workroom and allow edits. `SUCCESS` means the final human approval has already been processed.

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

## 4. Approve Experiment Plan

`POST /api/agent/actions/{agent_run_id}/approve`

Purpose: commit the user's final selected and edited experiments as immutable Elastic documents.

The frontend sends the final experiments from React state. These may differ from the original candidate items returned by polling.

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
