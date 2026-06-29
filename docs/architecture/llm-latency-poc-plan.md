# LLM Latency PoC Plan (Issue #13)

Status: Proposed (PoC scope)
Date: 2026-06-29
Scope: Analyst latency on the Python Agent Core turn path (analyst -> strategist -> writer -> reviewer)
Tracking: GitHub issue #13 "LLM Latency PoC"
Related: [orchestrator-latency-before-refactor.md](orchestrator-latency-before-refactor.md), [observability-telemetry-plan.md](observability-telemetry-plan.md), [adr/07-unified-observability.md](adr/07-unified-observability.md)

## 1. Why This Document Exists

Issue #13 proposes that the Analytics agent's >43s latency comes from repetitive
self-correction loops while turning probabilistic LLM output into deterministic
results, and lists three solution stages. Before writing fixes, this PoC must
first confirm that the issue's generic hypothesis matches what we actually
observe in LaunchPilot, then take only the applicable stages to a deep
implementation.

This document defines that work and its boundaries. It does not yet contain the
implementation; the instrumentation and profiler land on this branch after the
observation step in Section 4.

## 2. Scope

In scope for this PR:

- Stage 0 (verify): observe the existing telemetry from PRs #10-#12 and decide
  whether issue #13's hypothesis holds for our architecture.
- Stage 1 (quantify): make self-correction loops, LLM-call count, and timing per
  turn first-class, queryable telemetry.
- Stage 2 (lighten): reduce the analyst's per-turn LLM/tool round count by
  precomputing candidates deterministically and feeding metadata summaries
  instead of letting the model discover everything through tool calls.

Out of scope for this PR:

- Stage 3 (smaller / task-specific models for code generation). Deferred.

## 3. Hypothesis Mapping: Issue #13 vs LaunchPilot Reality

Issue #13 is written for a "raw CSV injected into the prompt -> generate Python
-> execute -> fix on error" pattern. LaunchPilot does not work that way, so the
hypothesis must be translated before it can be tested.

| Issue #13 claim | LaunchPilot reality | Applicable? |
| --- | --- | --- |
| Sequential generate-execute-fix loops dominate latency | The analyst is an ADK agent loop that emitted **6 function calls** in one worker call (~52.8s); the orchestrator runs analyst -> strategist -> writer serially. See [orchestrator-latency-before-refactor.md](orchestrator-latency-before-refactor.md) sections 5.5-5.6. | Yes, as a tool/model-round loop, not as a code-fix loop. |
| Raw CSV injection inflates input tokens and TTFT | CSV is parsed by Java into Elastic; the analyst prompt carries the user request and date range, not CSV rows (`apps/agent/app/agents/workers.py`). Evidence is pulled via Elastic tools (`apps/agent/app/tools/evidence.py`). | Partial. There is no raw-CSV prompt, but the analyst still discovers evidence through repeated tool calls. The lightweighting analog is precomputed candidate summaries. |
| Forcing deterministic code on a probabilistic model is inherently inefficient | The analyst is used as explorer + tool caller + data analyst + evidence selector + structured JSON generator in one call (section 6 of the latency doc). | Yes. Matches the latency doc's refactor implication (section 9): compute metric/channel candidates deterministically, use Flash to interpret precomputed candidates. |

Conclusion to validate in Stage 0: the real cost is the analyst's multi-round
evidence-discovery loop plus serial phase execution, not raw-CSV token volume.

## 4. Stage 0 - Verify Against Existing Telemetry

Goal: confirm the bottleneck before changing code. PRs #10-#12 established the
4-axis observability baseline (logs, metrics, traces, evals) across Java and
Python with shared correlation fields (`trace_id`, `thread_id`, `request_id`,
`workspace_id`, `campaign_id`).

Observation checklist for one representative E2E turn:

- [ ] End-to-end turn latency, split by Java / Python / Elastic / LLM-tool.
- [ ] Per-worker latency (`worker <kind>: gemini call done in <n>ms`,
  `apps/agent/app/agents/adk_agents.py:167`).
- [ ] Analyst function-call count for the turn (currently only visible as the
  ADK "non-text parts" warning, not as structured telemetry).
- [ ] Evidence tool invocations and their individual latencies (retriever spans,
  `apps/agent/app/telemetry/service.py:50`).
- [ ] Actual LLM calls vs the goal budget (`goal.budgets.max_llm_calls`,
  `apps/agent/app/telemetry/service.py:99`).

Exit criterion: a one-paragraph finding that either accepts or rejects the
mapped hypothesis in Section 3, with the trace/log evidence attached.

## 5. Stage 1 - Quantify Self-Correction Loops

Problem: the analyst's loop size is only observable today as an unstructured ADK
warning. We cannot query "how many model/tool rounds did this turn take" or
trend it across turns.

Plan:

1. In the worker run loop (`run_structured` / `run_text` in
   `apps/agent/app/agents/adk_agents.py`), count ADK events per call:
   function-call events (tool rounds), intermediate model responses, and the
   final response. Today `_collect()` only keeps `is_final_response()` and drops
   the rest.
2. Emit the counts through the existing telemetry facade
   (`apps/agent/app/telemetry/service.py`) so each worker span carries:
   `agent.worker.llm_round_count`, `agent.worker.function_call_count`,
   `agent.worker.elapsed_ms`.
3. Aggregate to the turn span: total LLM calls, total tool rounds, and the
   per-phase latency split, recorded in `record_turn_outcome`.

Success metric: for any turn we can read loop count, LLM-call count, and a
per-phase timing breakdown directly from telemetry, without grep-ing warnings.

## 6. Stage 2 - Lighten the Analyst Context

This is the issue's "data profiling and context lightweighting" stage, adapted
to the Elastic-evidence architecture, and it matches the latency doc's refactor
implication (Section 9, items 4-5).

Plan:

1. Precompute, in Python, a deterministic profile of the campaign's metrics and
   channels from Elastic (the equivalent of `df.info()` / `df.describe()` over
   `content_posts`), instead of letting the analyst discover them through
   multiple `query_metric_baseline` / `search_content_posts` tool calls.
2. Pass that compact profile summary into the analyst prompt as precomputed
   candidates.
3. Use the analyst (Flash) to interpret, select, and produce the structured
   signal schema from the precomputed candidates, targeting one or two model
   rounds instead of six.

Success metric: analyst function-call count and analyst latency drop materially
versus the Stage 0 baseline, with no regression in reviewer/eval quality (the
4th observability axis).

## 7. Risks and Notes

- Stage 2 changes the analyst's evidence path; reviewer/eval quality must be
  compared before and after so latency gains do not trade away grounding.
- Stage 1 must stay no-op-safe when tracing is disabled, consistent with the
  existing telemetry layer.
- All measurements should reuse the shared correlation fields so Java, Python,
  and Elastic timings line up on the same turn.

## 8. Definition of Done (this PR)

- Stage 0 finding recorded (hypothesis accepted or rejected with evidence).
- Stage 1 telemetry merged and visible per turn.
- Stage 2 lightweighting merged with a before/after latency and quality
  comparison.
- Stage 3 explicitly deferred to a follow-up issue.
