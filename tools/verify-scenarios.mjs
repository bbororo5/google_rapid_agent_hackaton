import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(fullPath) : [fullPath];
  });
}

function readJson(relativePath) {
  return JSON.parse(readFileSync(path.join(root, relativePath), "utf8"));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function unique(values) {
  return [...new Set(values)];
}

function fixture(step) {
  return readJson(step.fixture);
}

function requestFixture(step) {
  return step.request_fixture ? readJson(step.request_fixture) : null;
}

function getStep(scenario, id) {
  const step = scenario.steps.find((candidate) => candidate.id === id);
  assert(step, `Scenario ${scenario.id} is missing step ${id}`);
  return step;
}

function validateStepExpectations(scenario) {
  for (const step of scenario.steps) {
    const body = fixture(step);
    const request = requestFixture(step);
    const expect = step.expect ?? {};

    if ("ok" in expect) {
      assert(body.ok === expect.ok, `${step.id}: expected ok=${expect.ok}`);
    }

    if ("status" in expect) {
      assert(body.status === expect.status, `${step.id}: expected status=${expect.status}, got ${body.status}`);
    }

    if (expect.payload_is_null) {
      assert(body.payload === null, `${step.id}: expected payload to be null`);
    }

    if (expect.payload_is_present) {
      assert(body.payload && typeof body.payload === "object", `${step.id}: expected payload object`);
    }

    if (request) {
      assert(typeof request === "object", `${step.id}: request fixture must parse as object`);
    }
  }
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

function assertAgentRunIdStability(scenario) {
  const runAccepted = fixture(getStep(scenario, "run_agent"));
  const internalStartRequest = requestFixture(getStep(scenario, "internal_start_agent"));
  const internalStartResponse = fixture(getStep(scenario, "internal_start_agent"));
  const running = fixture(getStep(scenario, "poll_running"));
  const internalReady = fixture(getStep(scenario, "internal_poll_ready"));
  const publicReady = fixture(getStep(scenario, "poll_ready"));

  const ids = [
    runAccepted.agent_run_id,
    internalStartRequest.agent_run_id,
    internalStartResponse.agent_run_id,
    running.agent_run_id,
    internalReady.agent_run_id,
    publicReady.agent_run_id,
  ];
  assert(unique(ids).length === 1, `agent_run_id is not stable: ${ids.join(", ")}`);
}

function assertReadyPayloadCompatibility(scenario) {
  const internalReady = fixture(getStep(scenario, "internal_poll_ready"));
  const publicReady = fixture(getStep(scenario, "poll_ready"));

  assert(publicReady.status === "WAITING_FOR_APPROVAL", "public ready status must be WAITING_FOR_APPROVAL");
  assert(internalReady.status === "WAITING_FOR_APPROVAL", "internal ready status must be WAITING_FOR_APPROVAL");

  const publicPayload = publicReady.payload;
  const internalPayload = internalReady.payload;
  assert(publicPayload && internalPayload, "ready payloads must exist");

  assert(
    publicPayload.experiment_plan.id === internalPayload.experiment_plan.id,
    "public/internal experiment_plan.id must match",
  );
  assert(
    JSON.stringify(publicPayload.signals.map((signal) => signal.id)) ===
      JSON.stringify(internalPayload.signals.map((signal) => signal.id)),
    "public/internal signal IDs must match",
  );
  assert(
    JSON.stringify(publicPayload.hypotheses.map((hypothesis) => hypothesis.id)) ===
      JSON.stringify(internalPayload.hypotheses.map((hypothesis) => hypothesis.id)),
    "public/internal hypothesis IDs must match",
  );
}

function assertApprovalUsesReadyPlan(scenario) {
  const publicReady = fixture(getStep(scenario, "poll_ready"));
  const approvalRequest = requestFixture(getStep(scenario, "approve_plan"));

  assert(
    approvalRequest.experiment_plan_id === publicReady.payload.experiment_plan.id,
    "approval request must use experiment_plan.id from poll_ready payload",
  );

  const readyExperimentIds = publicReady.payload.experiment_plan.items.map((item) => item.id);
  const approvalExperimentIds = approvalRequest.final_experiments.map((item) => item.id);
  const missing = approvalExperimentIds.filter((id) => !readyExperimentIds.includes(id));
  assert(missing.length === 0, `approval final_experiments include unknown ready experiment IDs: ${missing.join(", ")}`);
}

function assertApprovalPersistenceLinks(scenario) {
  const approvalResponse = fixture(getStep(scenario, "approve_plan"));
  const approvalRequest = requestFixture(getStep(scenario, "approve_plan"));
  const growthBrief = fixture(getStep(scenario, "persist_growth_brief"));
  const calendarEvent = fixture(getStep(scenario, "persist_calendar_event"));

  assert(
    approvalResponse.growth_brief_id === growthBrief.growth_brief_id,
    "approval response growth_brief_id must match persisted growth_brief",
  );
  assert(growthBrief.calendar_event_ids.includes(calendarEvent.event_id), "growth_brief must list calendar event id");
  assert(
    approvalResponse.created_calendar_events.some((event) => event.event_id === calendarEvent.event_id),
    "approval response must list persisted calendar event id",
  );
  assert(
    approvalRequest.final_experiments.some((experiment) => experiment.id === calendarEvent.experiment_id),
    "calendar event must reference an approved final experiment",
  );
}

function assertEvidenceGrounding(scenario) {
  const known = evidenceRefIds();
  const publicReady = fixture(getStep(scenario, "poll_ready"));
  const refs = [
    ...publicReady.payload.signals.flatMap((signal) => signal.evidence_refs),
    ...publicReady.payload.hypotheses.flatMap((hypothesis) => hypothesis.supporting_evidence_refs),
  ];
  const missing = unique(refs).filter((ref) => !known.includes(ref));
  assert(missing.length === 0, `ready payload evidence refs are not grounded: ${missing.join(", ")}`);
}

function assertTraceLinks(scenario) {
  const trace = fixture(getStep(scenario, "emit_openinference_trace"));
  const internalReady = fixture(getStep(scenario, "internal_poll_ready"));

  assert(trace.trace_id === internalReady.agent_diagnostics.trace_id, "trace_id must match internal diagnostics");
  assert(trace.agent_run_id === internalReady.agent_run_id, "trace agent_run_id must match internal ready response");

  const spanIds = trace.spans.map((span) => span.span_id);
  const missingParents = trace.spans
    .map((span) => span.parent_span_id)
    .filter((parentId) => parentId !== null && !spanIds.includes(parentId));
  assert(missingParents.length === 0, `trace has missing parent span IDs: ${missingParents.join(", ")}`);

  const knownEvidence = evidenceRefIds();
  const documentIds = unique(
    trace.spans.flatMap((span) => span.attributes["retrieval.documents"] ?? []).map((document) => document["document.id"]),
  );
  const missingDocuments = documentIds.filter((id) => !knownEvidence.includes(id));
  assert(missingDocuments.length === 0, `trace retrieval documents are not grounded: ${missingDocuments.join(", ")}`);
}

function validateScenario(scenarioPath) {
  const scenario = JSON.parse(readFileSync(scenarioPath, "utf8"));
  assert(scenario.id, `${scenarioPath}: missing id`);
  assert(Array.isArray(scenario.steps), `${scenario.id}: missing steps`);
  assert(scenario.steps.length > 0, `${scenario.id}: steps must not be empty`);
  assert(Array.isArray(scenario.invariants), `${scenario.id}: missing invariants`);

  validateStepExpectations(scenario);
  assertAgentRunIdStability(scenario);
  assertReadyPayloadCompatibility(scenario);
  assertApprovalUsesReadyPlan(scenario);
  assertApprovalPersistenceLinks(scenario);
  assertEvidenceGrounding(scenario);
  assertTraceLinks(scenario);

  return scenario.id;
}

function main() {
  const scenarioFiles = walk(path.join(root, "scenarios")).filter((file) => file.endsWith(".scenario.json"));
  assert(scenarioFiles.length > 0, "No scenario files found");

  const scenarioIds = scenarioFiles.map(validateScenario);
  console.log(`Scenario verification passed (${scenarioIds.join(", ")}).`);
}

try {
  main();
} catch (error) {
  console.error(`Scenario verification failed: ${error.message}`);
  process.exitCode = 1;
}
