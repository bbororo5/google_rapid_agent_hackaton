# LaunchPilot Java-Elastic Data Contract

Status: Draft v0.1  
Boundary: Java Spring Boot Business Backend <-> Elastic Cloud Serverless  
Last updated: 2026-06-01

## Purpose

This contract defines the documents Java writes to Elastic and the invariants other components rely on.

Elastic is the single data store for LaunchPilot. In the MVP, Java writes four primary document families:

- `campaigns`: campaign working context while login/workspace membership is absent.
- `content_posts`: normalized SNS metric rows imported from CSV.
- `growth_briefs`: immutable approval records used for history and context restoration.
- `calendar_events`: calendar-optimized projections created from approved experiments.

Python Agent reads evidence from Elastic through MCP/tooling, but Java owns CSV ingestion and final approval persistence.

## Index Summary

| Index | Writer | Reader | Mutability | Purpose |
| --- | --- | --- | --- | --- |
| `campaigns` | Java seed/import flow | Frontend through Java, Python Agent context loader | Upsert by campaign | Primary working context for no-login MVP. |
| `content_posts` | Java `ImportService` | Python Agent evidence tools, Java import diagnostics | Upsert during import | Normalized SNS metric evidence from CSV. |
| `growth_briefs` | Java `BusinessDataService` | Java session restore, Python Agent parent context | Append-only | Approved experiment plan record. |
| `calendar_events` | Java `BusinessDataService` | Frontend calendar through Java | Append-only | Fast calendar view projection. |

## Core Invariants

- `workspace_id` is the tenant/data boundary. In the no-login MVP it may be a
  default namespace such as `demo_workspace`, but queries and writes must still
  carry it so future authorization does not require a data migration.
- `campaign_id` is the primary working context for the user experience and
  Agent Core prompt setup. It is not a replacement for `workspace_id`.
- `workspace_id` and `campaign_id` are required on every business document.
- Python Agent Core may resolve missing thread context by loading campaign and
  runtime thread memory from Elastic, but final approval persistence remains Java-owned.
- `growth_brief_id` is the central approval artifact ID.
- Every `calendar_events` document created by approval must reference exactly one `growth_brief_id`.
- `growth_briefs.final_experiments[].id` and `calendar_events.experiment_id` must refer to the same approved experiment IDs.
- Agent `evidence_refs` must point to stable source IDs such as `post_id` or `note_id`.
- `growth_briefs` and `calendar_events` are append-only. Do not update approved documents in place.
- Corrections create a new `growth_brief_id`, new `calendar_events`, and an incremented `version`.
- Approval for the same `thread_id` is single-use. Java must reject duplicate approval with `409 Conflict`.

## Refresh Policy

Recommended Java Elastic writes:

- CSV import to `content_posts`: `refresh=true` for demo predictability.
- Approval bulk insert to `growth_briefs` and `calendar_events`: `refresh=true`.

The frontend may still route to the calendar with local React state immediately after approval to avoid any perceived refresh latency.

## Bulk Approval Write

When the user approves experiments, Java must build and write:

1. One `growth_briefs` document.
2. One `calendar_events` document per approved experiment.

The bulk operation is treated as all-or-fail at the application level:

- If all documents are indexed successfully, Java returns `200 OK` to the frontend.
- If any document fails, Java returns failure and must not claim approval success.
- If Java cannot prove all documents were written, the approval response must be treated as failed.
- If retrying after an ambiguous failure, Java must use deterministic IDs to avoid duplicate artifacts.

## Index: `campaigns`

Purpose: campaign working context for Agent Core and UI while there is no login
or workspace membership model. It must always be interpreted inside a
`workspace_id` data boundary.

Document ID recommendation: `campaign_id`.

Required fields:

- `campaign_id`
- `workspace_id`
- `name`
- `description`
- `primary_channels`
- `target_metrics`
- `date_range`
- `created_at`
- `updated_at`

Optional fields:

- `creator_name`
- `brand_name`
- `goals`
- `constraints`
- `parent_brief_id`

`campaigns` is context, not evidence by itself. Python may use it to scope
searches and prompt setup, but claims still require evidence refs from approved
briefs, content posts, team notes, or metric aggregates.

## Index: `content_posts`

Purpose: source evidence for quantitative signal detection and baseline calculations.

Document ID recommendation: `post_id`.

Required fields:

- `post_id`
- `workspace_id`
- `campaign_id`
- `channel`
- `published_at`
- `title`
- `metrics`
- `source`
- `ingested_at`

`metrics` is intentionally flexible enough for hackathon CSVs, but known metrics should use stable names such as:

- `views`
- `likes`
- `comments`
- `shares`
- `saves`
- `save_rate`
- `engagement_rate`
- `follower_count`

## Index: `growth_briefs`

Purpose: immutable approved record and context restoration source for `parent_brief_id`.

Document ID recommendation: `growth_brief_id`.

Required fields:

- `growth_brief_id`
- `workspace_id`
- `campaign_id`
- `thread_id`
- `experiment_plan_id`
- `approved_by`
- `approved_at`
- `summary`
- `signals`
- `hypotheses`
- `final_experiments`
- `source_evidence_refs`
- `calendar_event_ids`
- `version`
- `created_at`

`growth_briefs` should preserve the exact approved final experiment text, including user edits made in the frontend before approval.

## Index: `calendar_events`

Purpose: query-optimized event documents for in-app calendar views.

Document ID recommendation: `event_id`.

Required fields:

- `event_id`
- `growth_brief_id`
- `experiment_id`
- `workspace_id`
- `campaign_id`
- `title`
- `channel`
- `scheduled_at`
- `target_metric`
- `success_criteria`
- `production_brief`
- `created_at`

`calendar_events` is a projection of `growth_briefs.final_experiments[]`. It may duplicate text fields intentionally to keep calendar reads simple and fast.

## ID Rules

Recommended prefixes:

- `post_` for content post evidence.
- `brief_` for approved growth briefs.
- `cal_` for calendar events.
- `thread_` for threads.
- `plan_` for experiment plans.
- `exp_` for experiment items.
- `hyp_` for hypotheses.
- `sig_` for signals.
- `imp_` for imports.

IDs should be stable across retries when Java is retrying the same logical operation.

## Open Decisions

- Whether to create a separate `team_notes` index for non-CSV qualitative evidence.
- Whether to retain raw CSV row payloads forever or only for the hackathon demo.
- Whether approved artifact corrections use `supersedes_growth_brief_id` in v0.2.
