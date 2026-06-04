import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import YAML from "yaml";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const root = process.cwd();
const contractsDir = path.join(root, "contracts");

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(fullPath) : [fullPath];
  });
}

function readText(relativePath) {
  return readFileSync(path.join(root, relativePath), "utf8");
}

function readJson(relativePath) {
  return JSON.parse(readText(relativePath));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function unique(values) {
  return [...new Set(values)];
}

function makeAjv() {
  const ajv = new Ajv2020({
    allErrors: true,
    strict: false,
    allowUnionTypes: true,
  });
  addFormats(ajv);
  return ajv;
}

function parseAllStructuredFiles(files) {
  const counts = { json: 0, ndjson: 0, yaml: 0 };

  for (const file of files) {
    const text = readFileSync(file, "utf8");

    if (file.endsWith(".json")) {
      JSON.parse(text);
      counts.json += 1;
      continue;
    }

    if (file.endsWith(".ndjson")) {
      const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
      assert(lines.length > 0, `${file} must contain at least one NDJSON line`);
      lines.forEach((line, index) => {
        try {
          JSON.parse(line);
        } catch (error) {
          throw new Error(`${file} line ${index + 1} is invalid JSON: ${error.message}`);
        }
      });
      counts.ndjson += 1;
      continue;
    }

    if (file.endsWith(".yaml") || file.endsWith(".yml")) {
      YAML.parse(text);
      counts.yaml += 1;
    }
  }

  return counts;
}

function compileSchemaValidator(ajv, schema, schemaPath, defName) {
  if (!defName) {
    return ajv.compile(schema);
  }

  const schemaId = schema.$id ?? `file://${schemaPath}`;
  return ajv.compile({ $ref: `${schemaId}#/$defs/${defName}` });
}

function validateExamplesWithSchema({ schemaPath, exampleGlobPrefix, defByFile = {} }) {
  const ajv = makeAjv();
  const schema = readJson(schemaPath);
  ajv.addSchema(schema, schema.$id ?? `file://${schemaPath}`);

  const exampleFiles = walk(path.join(root, exampleGlobPrefix)).filter((file) => file.endsWith(".json"));
  assert(exampleFiles.length > 0, `No JSON examples found under ${exampleGlobPrefix}`);

  for (const file of exampleFiles) {
    const basename = path.basename(file);
    const validate = compileSchemaValidator(ajv, schema, schemaPath, defByFile[basename]);
    const data = JSON.parse(readFileSync(file, "utf8"));
    const ok = validate(data);
    if (!ok) {
      const errors = ajv.errorsText(validate.errors, { separator: "\n" });
      throw new Error(`${path.relative(root, file)} does not match ${schemaPath}:\n${errors}`);
    }
  }
}

function openApiSchema(openApiPath, schemaName) {
  const doc = YAML.parse(readText(openApiPath));
  const schema = doc?.components?.schemas?.[schemaName];
  assert(schema, `Missing ${schemaName} in ${openApiPath}`);
  return schema;
}

function assertStatusEnumsMatch() {
  const publicStatuses = openApiSchema("contracts/01-frontend-java/openapi.yaml", "AgentRunStatus").enum;
  const internalStatuses = openApiSchema("contracts/02-java-python-agent/openapi.yaml", "AgentRunStatus").enum;

  assert(Array.isArray(publicStatuses), "Public AgentRunStatus enum missing");
  assert(Array.isArray(internalStatuses), "Internal AgentRunStatus enum missing");
  assert(
    JSON.stringify(publicStatuses) === JSON.stringify(internalStatuses),
    `AgentRunStatus enum mismatch\npublic: ${publicStatuses.join(", ")}\ninternal: ${internalStatuses.join(", ")}`,
  );
}

function evidenceRefIds() {
  const evidenceDir = path.join(root, "contracts/04-agent-elastic-mcp/examples");
  return unique(
    walk(evidenceDir)
      .filter((file) => file.endsWith("-response.json"))
      .flatMap((file) => JSON.parse(readFileSync(file, "utf8")).evidence_refs ?? [])
      .map((ref) => ref.ref_id),
  );
}

function assertEvidenceRefsAreGrounded() {
  const known = evidenceRefIds();
  const payloads = [
    "contracts/02-java-python-agent/examples/internal-stream-message.json",
    "contracts/05-agent-output/examples/final-agent-payload.json",
  ].map(readJson);

  const refs = payloads.flatMap((payload) => {
    const approvalBlock = (payload.blocks ?? []).find((block) => block.kind === "approval" && block.payload);
    const artifactBlock = (payload.blocks ?? []).find((block) => block.kind === "artifact" && block.content);
    const result = approvalBlock?.payload ?? artifactBlock?.content ?? payload.payload ?? payload;
    return [
      ...(result.signals ?? []).flatMap((signal) => signal.evidence_refs ?? []),
      ...(result.hypotheses ?? []).flatMap((hypothesis) => hypothesis.supporting_evidence_refs ?? []),
    ];
  });

  const missing = unique(refs).filter((ref) => !known.includes(ref));
  assert(missing.length === 0, `Evidence refs are not grounded by evidence examples: ${missing.join(", ")}`);
}

function assertAgentOutputInternalRefs() {
  const payload = readJson("contracts/05-agent-output/examples/final-agent-payload.json");
  const signalIds = payload.signals.map((signal) => signal.id);
  const hypothesisIds = payload.hypotheses.map((hypothesis) => hypothesis.id);

  const missingSignals = unique(payload.hypotheses.flatMap((hypothesis) => hypothesis.signal_ids)).filter(
    (id) => !signalIds.includes(id),
  );
  const missingHypotheses = unique(payload.experiment_plan.items.map((item) => item.hypothesis_id)).filter(
    (id) => !hypothesisIds.includes(id),
  );

  assert(missingSignals.length === 0, `Hypotheses reference missing signals: ${missingSignals.join(", ")}`);
  assert(missingHypotheses.length === 0, `Experiments reference missing hypotheses: ${missingHypotheses.join(", ")}`);
}

function assertElasticApprovalRefs() {
  const brief = readJson("contracts/03-java-elastic/examples/growth-brief.json");
  const event = readJson("contracts/03-java-elastic/examples/calendar-event.json");

  assert(brief.growth_brief_id === event.growth_brief_id, "Calendar event must reference growth brief");
  assert(brief.calendar_event_ids.includes(event.event_id), "Growth brief must list calendar event ID");
  assert(
    brief.final_experiments.some((experiment) => experiment.id === event.experiment_id),
    "Calendar event experiment_id must exist in growth brief final_experiments",
  );
}

function assertObservabilityTraceRefs() {
  const trace = readJson("contracts/06-observability/examples/agent-run-trace.json");

  assert(typeof trace.trace_id === "string" && trace.trace_id.length > 0, "Trace ID must be present");
  assert(typeof trace.thread_id === "string" && trace.thread_id.length > 0, "Trace thread_id must be present");

  const spanIds = trace.spans.map((span) => span.span_id);
  const missingParents = trace.spans
    .map((span) => span.parent_span_id)
    .filter((parentId) => parentId !== null && !spanIds.includes(parentId));
  assert(missingParents.length === 0, `Trace has missing parent spans: ${missingParents.join(", ")}`);

  const kinds = unique(trace.spans.map((span) => span.attributes["openinference.span.kind"]));
  const requiredKinds = ["AGENT", "CHAIN", "RETRIEVER", "TOOL", "LLM", "GUARDRAIL", "EVALUATOR"];
  const missingKinds = requiredKinds.filter((kind) => !kinds.includes(kind));
  assert(missingKinds.length === 0, `Trace is missing required OpenInference span kinds: ${missingKinds.join(", ")}`);

  const knownEvidence = evidenceRefIds();
  const retrievalDocumentIds = unique(
    trace.spans.flatMap((span) => span.attributes["retrieval.documents"] ?? []).map((document) => document["document.id"]),
  );
  const missingDocuments = retrievalDocumentIds.filter((id) => !knownEvidence.includes(id));
  assert(
    missingDocuments.length === 0,
    `Retriever span document IDs are not grounded by evidence examples: ${missingDocuments.join(", ")}`,
  );
}

function validateSchemaExamples() {
  validateExamplesWithSchema({
    schemaPath: "contracts/03-java-elastic/documents.schema.json",
    exampleGlobPrefix: "contracts/03-java-elastic/examples",
  });
  validateExamplesWithSchema({
    schemaPath: "contracts/04-agent-elastic-mcp/evidence-tools.schema.json",
    exampleGlobPrefix: "contracts/04-agent-elastic-mcp/examples",
    defByFile: {
      "search-content-posts-request.json": "searchContentPostsRequest",
      "search-content-posts-response.json": "searchContentPostsResponse",
      "query-metric-baseline-request.json": "queryMetricBaselineRequest",
      "query-metric-baseline-response.json": "queryMetricBaselineResponse",
      "search-team-notes-request.json": "searchTeamNotesRequest",
      "search-team-notes-response.json": "searchTeamNotesResponse",
      "load-growth-brief-context-request.json": "loadGrowthBriefContextRequest",
      "load-growth-brief-context-response.json": "loadGrowthBriefContextResponse",
      "evidence-tool-error-response.json": "toolErrorResponse",
    },
  });
  validateExamplesWithSchema({
    schemaPath: "contracts/05-agent-output/agent-output.schema.json",
    exampleGlobPrefix: "contracts/05-agent-output/examples",
    defByFile: {
      "signal-draft-output.json": "signalDraftOutput",
      "hypothesis-draft-output.json": "hypothesisDraftOutput",
      "experiment-plan-draft-output.json": "experimentPlanDraftOutput",
      "validation-report-pass.json": "validationReport",
      "validation-report-fail.json": "validationReport",
      "final-agent-payload.json": "agentResultPayload",
    },
  });
  validateExamplesWithSchema({
    schemaPath: "contracts/06-observability/openinference-traces.schema.json",
    exampleGlobPrefix: "contracts/06-observability/examples",
    defByFile: {
      "agent-run-trace.json": "trace",
      "retriever-span.json": "span",
      "tool-span.json": "span",
      "llm-span.json": "span",
      "reviewer-gate-span.json": "span",
      "evaluator-span.json": "span",
    },
  });
}

function main() {
  const files = walk(contractsDir);
  const counts = parseAllStructuredFiles(files);

  validateSchemaExamples();
  assertEvidenceRefsAreGrounded();
  assertAgentOutputInternalRefs();
  assertElasticApprovalRefs();
  assertObservabilityTraceRefs();

  console.log(`Contract verification passed (${counts.json} JSON, ${counts.ndjson} NDJSON, ${counts.yaml} YAML).`);
}

try {
  main();
} catch (error) {
  console.error(`Contract verification failed: ${error.message}`);
  process.exitCode = 1;
}
