# LaunchPilot Agent Structured Output & Reviewer Gate Contract

Status: Draft v0.1  
Boundary: Python Agent Service / Google ADK workers <-> Gemini structured generation <-> Reviewer Gate  
Last updated: 2026-06-01

## Purpose

This contract defines the structured outputs produced inside the Python Agent Service.

It intentionally avoids a single giant schema for every worker. Instead, each worker produces a narrow draft artifact, then the pipeline converges into the canonical `AgentResultPayload` already defined in:

- `contracts/01-frontend-java/openapi.yaml`
- `contracts/02-java-python-agent/openapi.yaml`
- `contracts/01-frontend-java/frontend-types.ts`

## Core Decision

Use multiple intermediate schemas, but one final canonical payload.

```text
Data Analyst Worker
  -> SignalDraftOutput

Data Strategist Worker
  -> HypothesisDraftOutput

Data Writer Worker
  -> ExperimentPlanDraftOutput

Reviewer Gate
  -> ValidationReport

Final Payload Assembler
  -> AgentResultPayload
```

## ADK Implementation Guidance

Google ADK workers that call tools should not be forced to do strict final JSON formatting in the same step.

Recommended pattern:

1. Tool-using worker calls LaunchPilot Evidence wrapper tools.
2. Worker stores evidence and draft text in shared state.
3. A formatter/normalizer step without tools emits the strict draft schema.
4. Reviewer Gate performs deterministic validation.
5. If validation fails, the orchestrator backtracks with `retry_instruction`.
6. If validation passes, Final Payload Assembler emits `AgentResultPayload`.

This keeps tool retrieval, creative reasoning, strict formatting, and validation as separate concerns.

## Worker Output Schemas

### SignalDraftOutput

Produced after quantitative evidence retrieval and signal detection.

Must include only evidence refs returned by:

- `search_content_posts`
- `query_metric_baseline`
- `search_team_notes`
- `load_growth_brief_context`

### HypothesisDraftOutput

Produced after strategy reasoning.

Each hypothesis must reference at least one existing signal ID and at least one valid evidence ref.

### ExperimentPlanDraftOutput

Produced after experiment design.

Each experiment item must reference an existing hypothesis ID. It must contain enough information for frontend approval without requiring another LLM call.

### ValidationReport

Produced by Reviewer Gate.

Reviewer Gate has two layers:

1. Deterministic validation in Python using Pydantic/JSON Schema and evidence ref set checks.
2. Optional Gemini-assisted critique or repair instruction generation.

The deterministic layer is authoritative. Gemini critique may explain or repair, but it must not override hard validation failures.

## Canonical Final Payload

The final payload must match `AgentResultPayload`:

```json
{
  "signals": [],
  "hypotheses": [],
  "experiment_plan": {}
}
```

Final payload rules:

- Field names use `snake_case`.
- IDs use the prefixes already defined in the API and Elastic contracts.
- `signals[].evidence_refs` must be a subset of known EvidenceRef IDs.
- `hypotheses[].supporting_evidence_refs` must be a subset of known EvidenceRef IDs.
- `hypotheses[].signal_ids` must reference existing signals.
- `experiment_plan.items[].hypothesis_id` must reference existing hypotheses.
- No raw Gemini reasoning, raw Elastic documents, ES|QL, Elasticsearch DSL, MCP transport messages, or provider error bodies may appear in the final payload.

## Reviewer Gate Issue Codes

Recommended issue codes:

- `SCHEMA_INVALID`
- `UNKNOWN_EVIDENCE_REF`
- `UNKNOWN_SIGNAL_ID`
- `UNKNOWN_HYPOTHESIS_ID`
- `EMPTY_EXPERIMENT_PLAN`
- `MISSING_SUCCESS_CRITERIA`
- `MISSING_SCHEDULE`
- `LOW_CONFIDENCE_WITHOUT_CAVEAT`
- `UNSUPPORTED_CHANNEL`
- `UNSAFE_OR_UNGROUNDED_CLAIM`

## Backtracking Rules

If validation fails:

- `passed` must be `false`.
- `severity` must be `blocking` when final payload cannot be emitted.
- `issues[]` must include machine-readable `path` values.
- `retry_instruction` must be concise and actionable.
- The orchestrator increments `retry_count`.
- After the configured retry limit, Python returns `FAILED` to Java.

## Anti-Patterns To Avoid

- Letting each worker invent its own field names.
- Treating JSON parse success as validation success.
- Asking a tool-using ADK worker to also produce the final strict response.
- Copying raw MCP or Elastic output into the frontend payload.
- Allowing evidence refs that were not returned by evidence tools.
- Letting Gemini override deterministic validator failures.

## Open Decisions

- Exact retry limit for Reviewer Gate failures.
- Whether formatter steps are implemented as separate `LlmAgent`s or deterministic Python normalization.
- Whether Gemini-assisted repair is enabled in the hackathon demo or deferred.
