import type { AgentDocument, AgentMessage, AgentObservation, AgentRunStatus, AgentStepSnapshot, AgentTimelineItem, AgentStreamRecoveryStatus, ExperimentItem, ExperimentPlannerEvent, ExperimentPlannerState, ToolCallLog } from "./experimentPlannerTypes";

const runningStatuses: AgentRunStatus[] = [
  "RUNNING_SIGNAL_DETECTION",
  "RUNNING_EVIDENCE_SEARCH",
  "RUNNING_HYPOTHESIS_GENERATION",
  "RUNNING_EXPERIMENT_GENERATION",
];

function isRunningStatus(status: AgentRunStatus): status is Exclude<AgentRunStatus, "PENDING" | "WAITING_FOR_APPROVAL" | "SUCCESS" | "FAILED" | "CANCELLED"> {
  return runningStatuses.includes(status);
}

function updateDraftExperiment(items: ExperimentItem[], experimentId: string, patch: Partial<ExperimentItem>) {
  return items.map((item) => (item.id === experimentId ? { ...item, ...patch } : item));
}

function mergeStep(steps: AgentStepSnapshot[], nextStep: AgentStepSnapshot | null | undefined) {
  if (!nextStep) return steps;
  const existingIndex = steps.findIndex((step) => step.id === nextStep.id);
  if (existingIndex < 0) return [...steps, nextStep].sort((a, b) => a.order - b.order);

  return steps.map((step, index) => (index === existingIndex ? { ...step, ...nextStep } : step)).sort((a, b) => a.order - b.order);
}

function mergeMessage(messages: AgentMessage[], nextMessage: AgentMessage | null | undefined) {
  if (!nextMessage) return messages;
  if (messages.some((message) => message.message_id === nextMessage.message_id)) return messages;
  return [...messages, nextMessage];
}

function mergeDocument(documents: AgentDocument[], nextDocument: AgentDocument | null | undefined) {
  if (!nextDocument) return documents;
  const existingIndex = documents.findIndex((document) => document.document_id === nextDocument.document_id);
  if (existingIndex < 0) return [...documents, nextDocument];
  return documents.map((document, index) => (index === existingIndex ? { ...document, ...nextDocument } : document));
}

function mergeToolLog(toolLogs: ToolCallLog[], nextToolLog: ToolCallLog | null | undefined) {
  if (!nextToolLog) return toolLogs;
  const existingIndex = toolLogs.findIndex((toolLog) => toolLog.sequence === nextToolLog.sequence && toolLog.tool_name === nextToolLog.tool_name);
  if (existingIndex < 0) return [...toolLogs, nextToolLog].sort((a, b) => a.sequence - b.sequence);
  return toolLogs.map((toolLog, index) => (index === existingIndex ? { ...toolLog, ...nextToolLog } : toolLog)).sort((a, b) => a.sequence - b.sequence);
}

function mergeTimelineItem(timelineItems: AgentTimelineItem[], event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }) {
  const sequence = event.event.sequence;
  if (typeof sequence !== "number") return timelineItems;

  const item = timelineItemFromEvent(event, sequence);
  if (!item) return timelineItems;

  const existingIndex = timelineItems.findIndex((timelineItem) => timelineItem.id === item.id);
  if (existingIndex < 0) return [...timelineItems, item].sort((a, b) => a.sequence - b.sequence);

  return timelineItems
    .map((timelineItem, index) => (index === existingIndex ? { ...timelineItem, ...item, sequence: timelineItem.sequence } : timelineItem))
    .sort((a, b) => a.sequence - b.sequence);
}

function timelineItemFromEvent(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }, sequence: number): AgentTimelineItem | null {
  if (event.event.message?.role === "assistant") {
    return { id: `message:${event.event.message.message_id}`, sequence, kind: "assistant_message", message: event.event.message };
  }

  if (event.event.document) {
    return { id: `document:${event.event.document.document_id}`, sequence, kind: "document", document: event.event.document };
  }

  if (event.event.observation) {
    return { id: `observation:${event.event.observation.id}`, sequence, kind: "observation", observation: event.event.observation };
  }

  if (event.event.tool_call) {
    return {
      id: `tool:${event.event.tool_call.sequence}:${event.event.tool_call.tool_name}`,
      sequence,
      kind: "tool",
      tool: event.event.tool_call,
    };
  }

  return null;
}

function nextSequence(current: number, sequence: number | null | undefined) {
  return typeof sequence === "number" ? Math.max(current, sequence) : current;
}

function cancelledStateFromTimeline(
  state: {
    agentRunId: string;
    messages?: AgentMessage[];
    documents?: AgentDocument[];
    observations?: AgentObservation[];
    toolLogs?: ToolCallLog[];
    timelineItems?: AgentTimelineItem[];
    lastReceivedSequence?: number;
    recoveryStatus?: AgentStreamRecoveryStatus;
  },
  message: string,
  overrides?: {
    messages?: AgentMessage[];
    documents?: AgentDocument[];
    observations?: AgentObservation[];
    toolLogs?: ToolCallLog[];
    timelineItems?: AgentTimelineItem[];
    lastReceivedSequence?: number;
    recoveryStatus?: AgentStreamRecoveryStatus;
  }
): ExperimentPlannerState {
  return {
    tag: "analysis_cancelled",
    agentRunId: state.agentRunId,
    message,
    messages: overrides?.messages ?? state.messages ?? [],
    documents: overrides?.documents ?? state.documents ?? [],
    observations: overrides?.observations ?? state.observations ?? [],
    toolLogs: overrides?.toolLogs ?? state.toolLogs ?? [],
    timelineItems: overrides?.timelineItems ?? state.timelineItems ?? [],
    lastReceivedSequence: overrides?.lastReceivedSequence ?? state.lastReceivedSequence ?? 0,
    recoveryStatus: overrides?.recoveryStatus ?? state.recoveryStatus ?? "idle",
  };
}

const defaultQuestion = "";

function questionFromState(state: ExperimentPlannerState) {
  return "question" in state ? state.question : defaultQuestion;
}

export const initialExperimentPlannerState: ExperimentPlannerState = { tag: "idle", question: defaultQuestion };

export function experimentPlannerReducer(state: ExperimentPlannerState, event: ExperimentPlannerEvent): ExperimentPlannerState {
  switch (event.type) {
    case "UPDATE_QUESTION":
      if ("question" in state) {
        return { ...state, question: event.question };
      }
      return state;

    case "SELECT_CSV":
      return { tag: "csv_selected", file: event.file, question: questionFromState(state) };

    case "IMPORT_REQUESTED":
      if (state.tag !== "csv_selected" && state.tag !== "import_failed") return state;
      return { tag: "importing_csv", file: state.file ?? eventFileFallback(), question: state.question };

    case "IMPORT_SUCCEEDED":
      if (state.tag !== "importing_csv") return state;
      return { tag: "import_succeeded", file: state.file, importResult: event.importResult, question: state.question };

    case "IMPORT_FAILED":
      if (state.tag !== "importing_csv") return { tag: "import_failed", question: questionFromState(state), message: event.message };
      return { tag: "import_failed", file: state.file, question: state.question, message: event.message };

    case "RUN_AGENT_REQUESTED":
      if (state.tag === "import_succeeded") {
        return { tag: "starting_analysis", source: { kind: "csv_import", importResult: state.importResult, question: state.question } };
      }
      if (state.tag === "restored_context") {
        return {
          tag: "starting_analysis",
          source: {
            kind: "continued_brief",
            parentBriefId: state.parentBriefId,
            previousHypothesis: state.previousHypothesis,
            previousActionSummary: state.previousActionSummary,
            observedResultSummary: state.observedResultSummary,
            continuityPrompt: state.continuityPrompt,
          },
        };
      }
      return state;

    case "RUN_AGENT_ACCEPTED":
      if (state.tag !== "starting_analysis") return state;
      return { tag: "analysis_pending", agentRunId: event.agentRunId, streamUrl: event.streamUrl, snapshotUrl: event.snapshotUrl, status: "PENDING", toolLogs: [] };

    case "RUN_AGENT_FAILED":
      return { tag: "analysis_failed", message: event.message, recoverable: true };

    case "STREAM_CONNECT_REQUESTED":
      if (state.tag !== "analysis_pending") return state;
      return {
        tag: "stream_connecting",
        agentRunId: state.agentRunId,
        streamUrl: state.streamUrl,
        snapshotUrl: state.snapshotUrl,
        toolLogs: state.toolLogs,
        messages: [],
        documents: [],
        timelineItems: [],
        lastReceivedSequence: 0,
        recoveryStatus: "idle",
      };

    case "STREAM_CONNECTED":
      if (state.tag !== "stream_connecting") return state;
      return {
        tag: "analysis_running",
        agentRunId: state.agentRunId,
        streamUrl: state.streamUrl,
        snapshotUrl: state.snapshotUrl,
        status: "RUNNING_SIGNAL_DETECTION",
        currentStage: null,
        steps: [],
        messages: state.messages,
        documents: state.documents,
        observations: [],
        toolLogs: state.toolLogs,
        timelineItems: state.timelineItems,
        lastReceivedSequence: state.lastReceivedSequence,
        recoveryStatus: state.recoveryStatus,
      };

    case "STREAM_EVENT_RECEIVED": {
      if (
        state.tag !== "stream_connecting" &&
        state.tag !== "analysis_running" &&
        state.tag !== "signal_review" &&
        state.tag !== "waiting_for_approval" &&
        state.tag !== "editing_plan" &&
        state.tag !== "approving"
      ) {
        return state;
      }
      if (typeof event.event.sequence === "number" && event.event.sequence <= state.lastReceivedSequence) {
        return state;
      }

      if (event.event.type === "connection.resume_accepted") {
        return { ...state, recoveryStatus: "resuming" };
      }

      if (event.event.type === "connection.replay_started") {
        return { ...state, recoveryStatus: event.event.replay_scope === "full_timeline" ? "full_syncing" : "replaying" };
      }

      if (event.event.type === "connection.replay_completed") {
        return { ...state, recoveryStatus: "idle" };
      }

      if (event.event.type === "connection.full_sync_required") {
        return { ...state, recoveryStatus: "full_syncing" };
      }

      if (event.event.type === "connection.reauth_required") {
        return { tag: "analysis_failed", agentRunId: state.agentRunId, message: "Agent stream requires re-authentication.", recoverable: true };
      }

      if (event.event.type === "connection.session_expired") {
        return { tag: "analysis_failed", agentRunId: state.agentRunId, message: "Agent stream session expired.", recoverable: true };
      }

      const base =
        state.tag === "stream_connecting"
          ? {
              agentRunId: state.agentRunId,
              streamUrl: state.streamUrl,
              snapshotUrl: state.snapshotUrl,
              steps: [],
              messages: state.messages,
              documents: state.documents,
              observations: [],
              toolLogs: state.toolLogs,
              timelineItems: state.timelineItems,
              lastReceivedSequence: state.lastReceivedSequence,
              recoveryStatus: state.recoveryStatus,
            }
          : state;
      const steps = mergeStep(base.steps, event.event.step);
      const messages = mergeMessage(base.messages, event.event.message);
      const documents = mergeDocument(base.documents, event.event.document);
      const observations = event.event.observation ? [...base.observations, event.event.observation] : base.observations;
      const toolLogs = mergeToolLog(base.toolLogs, event.event.tool_call);
      const timelineItems = mergeTimelineItem(base.timelineItems, event);
      const lastReceivedSequence = nextSequence(base.lastReceivedSequence, event.event.sequence);

      if (event.event.type === "signal.detected" && event.event.payload?.signals[0]) {
        return {
          tag: "signal_review",
          agentRunId: base.agentRunId,
          streamUrl: base.streamUrl,
          snapshotUrl: base.snapshotUrl,
          status: event.event.status && isRunningStatus(event.event.status) ? event.event.status : "RUNNING_HYPOTHESIS_GENERATION",
          currentStage: event.event.step?.stage ?? null,
          signal: event.event.payload.signals[0],
          payload: event.event.payload,
          steps,
          messages,
          documents,
          observations,
          toolLogs,
          timelineItems,
          lastReceivedSequence,
          recoveryStatus: base.recoveryStatus,
        };
      }

      if (event.event.type === "approval.requested" && event.event.approval) {
        const payload = event.event.approval.payload;
        return {
          tag: "waiting_for_approval",
          agentRunId: base.agentRunId,
          streamUrl: base.streamUrl,
          snapshotUrl: base.snapshotUrl,
          approvalId: event.event.approval.approval_id,
          payload,
          selectedExperimentIds: payload.experiment_plan.items.map((item) => item.id),
          draftExperiments: payload.experiment_plan.items,
          steps,
          messages,
          documents,
          observations,
          toolLogs,
          timelineItems,
          lastReceivedSequence,
          recoveryStatus: base.recoveryStatus,
        };
      }

      if (event.event.type === "approval.committed" && event.event.approval_result) {
        const finalExperiments = "draftExperiments" in base ? base.draftExperiments.filter((experiment) => base.selectedExperimentIds.includes(experiment.id)) : [];
        return {
          tag: "approved",
          agentRunId: base.agentRunId,
          approval: {
            ok: true,
            message: "Human approval processed successfully.",
            growth_brief_id: event.event.approval_result.growth_brief_id,
            created_calendar_events: event.event.approval_result.created_calendar_events,
            persisted_at: event.event.approval_result.persisted_at,
          },
          approvalResult: event.event.approval_result,
          calendarEvents: event.event.approval_result.created_calendar_events,
          finalExperiments,
          messages,
          documents,
          observations,
          toolLogs,
          timelineItems,
          lastReceivedSequence,
          recoveryStatus: base.recoveryStatus,
        };
      }

      if (event.event.type === "run.cancelled") {
        return cancelledStateFromTimeline(base, "Agent run cancelled.", {
          messages,
          documents,
          observations,
          toolLogs,
          timelineItems,
          lastReceivedSequence,
          recoveryStatus: base.recoveryStatus,
        });
      }

      if (event.event.type === "run.failed") {
        return { tag: "analysis_failed", agentRunId: base.agentRunId, message: event.event.error_message ?? "Agent run failed.", recoverable: true };
      }

      if (state.tag === "signal_review") {
        return {
          ...state,
          status: event.event.status && isRunningStatus(event.event.status) ? event.event.status : state.status,
          currentStage: event.event.step?.stage ?? state.currentStage,
          steps,
          messages,
          documents,
          observations,
          toolLogs,
          timelineItems,
          lastReceivedSequence,
          recoveryStatus: base.recoveryStatus,
        };
      }

      if (state.tag !== "stream_connecting" && state.tag !== "analysis_running" && (!event.event.status || !isRunningStatus(event.event.status))) {
        return {
          ...state,
          steps,
          messages,
          documents,
          observations,
          toolLogs,
          timelineItems,
          lastReceivedSequence,
          recoveryStatus: base.recoveryStatus,
        };
      }

      if (!event.event.status || !isRunningStatus(event.event.status)) {
        return {
          tag: "analysis_running",
          agentRunId: base.agentRunId,
          streamUrl: base.streamUrl,
          snapshotUrl: base.snapshotUrl,
          status: "RUNNING_EVIDENCE_SEARCH",
          currentStage: event.event.step?.stage ?? null,
          steps,
          messages,
          documents,
          observations,
          toolLogs,
          timelineItems,
          lastReceivedSequence,
          recoveryStatus: base.recoveryStatus,
        };
      }

      return {
        tag: "analysis_running",
        agentRunId: base.agentRunId,
        streamUrl: base.streamUrl,
        snapshotUrl: base.snapshotUrl,
        status: event.event.status,
        currentStage: event.event.step?.stage ?? null,
        steps,
        messages,
        documents,
        observations,
        toolLogs,
        timelineItems,
        lastReceivedSequence,
        recoveryStatus: base.recoveryStatus,
      };
    }

    case "SIGNAL_CONFIRMED":
      if (state.tag !== "signal_review") return state;
      return {
        tag: "analysis_running",
        agentRunId: state.agentRunId,
        streamUrl: state.streamUrl,
        snapshotUrl: state.snapshotUrl,
        status: state.status,
        currentStage: state.currentStage,
        steps: state.steps,
        messages: state.messages,
        documents: state.documents,
        observations: state.observations,
        toolLogs: state.toolLogs,
        timelineItems: state.timelineItems,
        lastReceivedSequence: state.lastReceivedSequence,
        recoveryStatus: state.recoveryStatus,
      };

    case "SNAPSHOT_RECOVERED":
      if (state.tag !== "stream_connecting" && state.tag !== "analysis_running") return state;
      if (event.snapshot.status === "WAITING_FOR_APPROVAL" && event.snapshot.payload) {
        const existingSteps = "steps" in state ? state.steps : [];
        const existingMessages = "messages" in state ? state.messages : [];
        const existingDocuments = "documents" in state ? state.documents : [];
        const existingObservations = "observations" in state ? state.observations : [];
        const existingTimelineItems = "timelineItems" in state ? state.timelineItems : [];
        return {
          tag: "waiting_for_approval",
          agentRunId: event.snapshot.agent_run_id,
          streamUrl: "streamUrl" in state ? state.streamUrl : `/api/agent/runs/${event.snapshot.agent_run_id}/stream`,
          snapshotUrl: "snapshotUrl" in state ? state.snapshotUrl : `/api/agent/runs/${event.snapshot.agent_run_id}`,
          approvalId: "snapshot_recovered",
          payload: event.snapshot.payload,
          selectedExperimentIds: event.snapshot.payload.experiment_plan.items.map((item) => item.id),
          draftExperiments: event.snapshot.payload.experiment_plan.items,
          steps: existingSteps,
          messages: existingMessages,
          documents: existingDocuments,
          observations: existingObservations,
          toolLogs: event.snapshot.tool_call_logs,
          timelineItems: existingTimelineItems,
          lastReceivedSequence: "lastReceivedSequence" in state ? state.lastReceivedSequence : 0,
          recoveryStatus: "recoveryStatus" in state ? state.recoveryStatus : "idle",
        };
      }
      if (event.snapshot.status === "FAILED") {
        return { tag: "analysis_failed", agentRunId: event.snapshot.agent_run_id, message: event.snapshot.error_message ?? "Agent run failed.", recoverable: true };
      }
      if (!isRunningStatus(event.snapshot.status)) return state;
      return {
        tag: "analysis_running",
        agentRunId: event.snapshot.agent_run_id,
        streamUrl: "streamUrl" in state ? state.streamUrl : `/api/agent/runs/${event.snapshot.agent_run_id}/stream`,
        snapshotUrl: "snapshotUrl" in state ? state.snapshotUrl : `/api/agent/runs/${event.snapshot.agent_run_id}`,
        status: event.snapshot.status,
        currentStage: event.snapshot.current_stage,
        steps: "steps" in state ? state.steps : [],
        messages: "messages" in state ? state.messages : [],
        documents: "documents" in state ? state.documents : [],
        observations: "observations" in state ? state.observations : [],
        toolLogs: event.snapshot.tool_call_logs,
        timelineItems: "timelineItems" in state ? state.timelineItems : [],
        lastReceivedSequence: "lastReceivedSequence" in state ? state.lastReceivedSequence : 0,
        recoveryStatus: "recoveryStatus" in state ? state.recoveryStatus : "idle",
      };

    case "STREAM_FAILED":
      return {
        tag: "analysis_failed",
        agentRunId: event.agentRunId,
        message: event.message,
        recoverable: true,
      };

    case "EDIT_EXPERIMENT":
      if (state.tag !== "waiting_for_approval" && state.tag !== "editing_plan") return state;
      return {
        ...state,
        tag: "editing_plan",
        dirty: true,
        draftExperiments: updateDraftExperiment(state.draftExperiments, event.experimentId, event.patch),
      };

    case "APPROVE_SENT":
      if (state.tag !== "waiting_for_approval" && state.tag !== "editing_plan") return state;
      return {
        tag: "approving",
        agentRunId: state.agentRunId,
        streamUrl: state.streamUrl,
        snapshotUrl: state.snapshotUrl,
        approvalId: state.approvalId,
        payload: state.payload,
        selectedExperimentIds: state.selectedExperimentIds,
        draftExperiments: state.draftExperiments,
        steps: state.steps,
        messages: state.messages,
        documents: state.documents,
        observations: state.observations,
        toolLogs: state.toolLogs,
        timelineItems: state.timelineItems,
        lastReceivedSequence: state.lastReceivedSequence,
        recoveryStatus: state.recoveryStatus,
      };

    case "RUN_COMPLETED":
      if (state.tag !== "approving") return state;
      return {
        tag: "approved",
        agentRunId: state.agentRunId,
        approval: event.approval,
        approvalResult: null,
        calendarEvents: event.approval.created_calendar_events,
        finalExperiments: state.draftExperiments.filter((experiment) => state.selectedExperimentIds.includes(experiment.id)),
        messages: state.messages,
        documents: state.documents,
        observations: state.observations,
        toolLogs: state.toolLogs,
        timelineItems: state.timelineItems,
        lastReceivedSequence: state.lastReceivedSequence,
        recoveryStatus: state.recoveryStatus,
      };

    case "APPROVE_FAILED":
      return { tag: "approval_failed", message: event.message, recoverable: true };

    case "CANCEL_SENT":
      if (!("agentRunId" in state) || !state.agentRunId) return state;
      return cancelledStateFromTimeline({ ...state, agentRunId: state.agentRunId }, event.reason ?? "Agent run cancelled.");

    case "REJECT_SENT":
      if (!("agentRunId" in state) || !state.agentRunId) return state;
      return cancelledStateFromTimeline({ ...state, agentRunId: state.agentRunId }, event.reason ?? "Approval rejected.");

    case "RUN_CANCELLED":
      if (!("agentRunId" in state) || !state.agentRunId) return state;
      return cancelledStateFromTimeline({ ...state, agentRunId: state.agentRunId }, event.message);

    case "RESET":
      return initialExperimentPlannerState;

    default:
      return state;
  }
}

function eventFileFallback(): File {
  return new File([], "selected.csv", { type: "text/csv" });
}
