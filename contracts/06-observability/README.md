# LaunchPilot OpenInference Observability & Reflection Contract

Status: Draft v0.1  
Boundary: Python Agent Service / Google ADK <-> OpenInference / OpenTelemetry OTLP <-> Phoenix or Arize  
Last updated: 2026-06-01

## Purpose

This contract defines how LaunchPilot threads are traced and how trace IDs connect back to Java polling responses.

This is not an application API contract. It is a trace semantics contract based on OpenInference conventions over OpenTelemetry.

## Product Boundary

LaunchPilot may export traces to Phoenix open-source, Phoenix Cloud, or Arize depending on deployment. The span attributes in this contract use OpenInference semantic conventions so the telemetry can be consumed consistently.

Phoenix receives traces over OTLP. OpenInference defines the AI-specific span kinds and attributes.

## Required Trace Identity

Every thread trace must include these identifiers:

- `trace_id`: OpenTelemetry trace ID. This should be surfaced to Java as `agent_diagnostics.trace_id`.
- `thread_id`: Java-generated run ID, stored in `metadata.thread_id`.
- `session.id`: stable session key. Recommended value: `workspace_id:campaign_id`.
- `metadata.workspace_id`
- `metadata.campaign_id`
- `metadata.parent_brief_id` when present.

Java should not expose full trace attributes to the frontend. Java may expose only `agent_diagnostics.trace_id` internally or in debug UI.

## Span Hierarchy

Required shape:

```text
AGENT launchpilot.thread
  CHAIN launchpilot.orchestrator
    PROMPT launchpilot.prompt.render
    RETRIEVER launchpilot.evidence.search_content_posts
      TOOL search_content_posts
    RETRIEVER launchpilot.evidence.query_metric_baseline
      TOOL query_metric_baseline
    RETRIEVER launchpilot.evidence.search_team_notes
      TOOL search_team_notes
    LLM launchpilot.gemini.signal_detection
    LLM launchpilot.gemini.hypothesis_generation
    LLM launchpilot.gemini.experiment_generation
    GUARDRAIL launchpilot.reviewer_gate
    EVALUATOR launchpilot.validation
```

Optional span:

```text
RETRIEVER launchpilot.memory.load_growth_brief_context
  TOOL load_growth_brief_context
```

## OpenInference Span Kinds

Use `openinference.span.kind` on every AI span.

Required kinds for LaunchPilot:

- `AGENT`: whole thread.
- `CHAIN`: orchestrator pipeline or worker handoff.
- `PROMPT`: prompt/template rendering.
- `RETRIEVER`: evidence retrieval from Elastic.
- `TOOL`: LaunchPilot Evidence wrapper call or Phoenix MCP reflection call.
- `LLM`: Gemini model call.
- `GUARDRAIL`: Reviewer Gate checks.
- `EVALUATOR`: deterministic validation or LLM-as-a-judge evaluation summary.

## Required Common Attributes

Every span in this contract should include:

- `openinference.span.kind`
- `input.mime_type`
- `input.value`
- `output.mime_type`
- `output.value`
- `metadata`
- `session.id`

`input.value`, `output.value`, and `metadata` should be JSON strings when the value is structured.

## Metadata Contract

The `metadata` JSON string should include:

```json
{
  "thread_id": "run_20260601_001",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "worker": "Data Analyst Worker",
  "stage": "RUNNING_EVIDENCE_SEARCH",
  "retry_count": 0,
  "parent_brief_id": null
}
```

## Retriever Span Contract

Retriever spans must include:

- `openinference.span.kind`: `RETRIEVER`
- `retrieval.documents`
- `metadata.thread_id`
- `metadata.tool_name`

Each retrieved document must include:

- `document.id`
- `document.content`
- `document.score`
- `document.metadata`

`document.id` must match the `EvidenceRef.ref_id` that can later appear in final payloads.

## Tool Span Contract

Tool spans must include:

- `openinference.span.kind`: `TOOL`
- `tool.name`
- `tool.parameters`
- `input.value`
- `output.value`

Tool names must match `contracts/04-agent-elastic-mcp/README.md` wrapper names:

- `search_content_posts`
- `query_metric_baseline`
- `search_team_notes`
- `load_growth_brief_context`

Phoenix reflection tools, if used, should be named with `phoenix_` prefix, for example:

- `phoenix_get_traces`
- `phoenix_get_evaluations`

## LLM Span Contract

LLM spans must include:

- `openinference.span.kind`: `LLM`
- `llm.input_messages.*`
- `llm.output_messages.*`
- `input.value`
- `output.value`
- `metadata.model_provider`: `google`
- `metadata.model_name`: Gemini model ID used by the run.

Do not store secrets, API keys, or full private credentials in any span.

## Reviewer Gate Span Contract

Reviewer Gate spans use:

- `openinference.span.kind`: `GUARDRAIL`
- `input.value`: draft payload or summarized validation input.
- `output.value`: `ValidationReport`.
- `metadata.validator_passed`
- `metadata.backtrack_count`

The deterministic validator result is authoritative. LLM critique may be captured as a child `LLM` or `EVALUATOR` span, but it must not override deterministic validation failures.

## Reflection Contract

Phoenix/Arize reflection is an input to the agent's self-correction loop.

Recommended span shape:

```text
TOOL phoenix_get_evaluations
EVALUATOR launchpilot.reflection.failure_pattern_summary
```

Reflection output should summarize prior failure patterns, not inject raw long traces into the prompt.

The reflection summary may be stored in `metadata.reflection_summary` or `output.value` of an `EVALUATOR` span.

## Java Mapping

Python internal status responses may include:

```json
{
  "agent_diagnostics": {
    "trace_id": "trc_20260601_001",
    "validator_passed": true,
    "backtrack_count": 0
  }
}
```

`trace_id` should refer to the OpenTelemetry trace ID or a stable Phoenix trace alias. The examples use `trc_*` as a human-readable alias for hackathon fixtures.

## Redaction Rules

Never emit these into spans:

- API keys or credentials.
- Full raw CSV files.
- Full raw prompt chains when they include secrets.
- User personal data beyond demo identifiers.
- Raw provider exception bodies if they include request headers.

Prefer concise JSON summaries over large raw payloads.

## Open Decisions

- Whether the deployment target is Phoenix open-source, Phoenix Cloud, or Arize AX.
- Exact Gemini model metadata key naming if auto-instrumentation emits provider-specific attributes.
- Whether Java should expose `trace_id` in non-debug frontend responses.
