import type { AgentDocument, AgentMessage, AgentThreadObservation, AgentResultPayload, AgentTimelineItem, AgentStreamRecoveryStatus, ExperimentItem, ExperimentPlannerEvent, ExperimentPlannerState, ToolCallLog } from "./experimentPlannerTypes";

function updateDraftExperiment(items: ExperimentItem[], experimentId: string, patch: Partial<ExperimentItem>) {
  return items.map((item) => (item.id === experimentId ? { ...item, ...patch } : item));
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

function mergeTimelineItems(timelineItems: AgentTimelineItem[], items: AgentTimelineItem[]) {
  return items.reduce((nextItems, item) => {
    const existingIndex = nextItems.findIndex((timelineItem) => timelineItem.id === item.id);
    if (existingIndex < 0) return [...nextItems, item].sort((a, b) => a.sequence - b.sequence);
    return nextItems
      .map((timelineItem, index) => (index === existingIndex ? { ...timelineItem, ...item, sequence: timelineItem.sequence } : timelineItem))
      .sort((a, b) => a.sequence - b.sequence);
  }, timelineItems);
}

function textFromStreamMessage(message: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }) {
  return message.message.blocks
    .filter((block) => block.kind === "text")
    .map((block) => block.text)
    .join("\n")
    .trim();
}

function documentsFromStreamMessage(message: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): AgentDocument[] {
  return message.message.blocks
    .filter((block) => block.kind === "markdown_document")
    .map((block) => ({
      document_id: block.id,
      kind: block.id.includes("evidence_scan") ? ("evidence_scan" as const) : ("generic" as const),
      title: block.title,
      format: "markdown" as const,
      summary: block.summary ?? block.title,
      content: block.markdown,
    }));
}

function toolLogsFromStreamMessage(message: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): ToolCallLog[] {
  return message.message.blocks
    .filter((block) => block.kind === "activity")
    .map((block, index) => ({
      sequence: message.message.sequence * 100 + index,
      tool_name: block.id ?? block.title,
      status: block.status === "failed" ? "FAILED" : block.status === "done" ? "SUCCESS" : block.status === "running" ? "RUNNING" : "PENDING",
      duration_ms: null,
      error_message: block.status === "failed" ? block.detail ?? null : null,
    }));
}

function timelineItemsFromStreamMessage(message: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): AgentTimelineItem[] {
  const sequence = message.message.sequence;
  const text = textFromStreamMessage(message);
  const textItem: AgentTimelineItem[] =
    text && message.message.role === "assistant"
      ? [{ id: `message:${message.message.id}`, sequence, kind: "assistant_message", message: { message_id: message.message.id, role: "assistant", content: text } }]
      : [];
  const documentItems: AgentTimelineItem[] = documentsFromStreamMessage(message).map((document) => ({
    id: `document:${document.document_id}`,
    sequence,
    kind: "document",
    document,
  }));
  const toolItems: AgentTimelineItem[] = toolLogsFromStreamMessage(message).map((tool) => ({
    id: `tool:${tool.sequence}:${tool.tool_name}`,
    sequence,
    kind: "tool",
    tool,
  }));
  return [...textItem, ...documentItems, ...toolItems];
}

function payloadFromStreamMessage(message: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): AgentResultPayload | null {
  const approvalBlock = message.message.blocks.find((block) => block.kind === "approval" && block.payload);
  if (approvalBlock?.kind === "approval" && approvalBlock.payload) return approvalBlock.payload;

  const artifactBlock = message.message.blocks.find((block) => block.kind === "artifact" && isAgentResultPayload(block.content));
  if (artifactBlock?.kind === "artifact" && isAgentResultPayload(artifactBlock.content)) return artifactBlock.content;

  return null;
}

function isAgentResultPayload(value: unknown): value is AgentResultPayload {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<AgentResultPayload>;
  return Array.isArray(candidate.signals) && Array.isArray(candidate.hypotheses) && typeof candidate.experiment_plan === "object" && candidate.experiment_plan !== null;
}

function nextSequence(current: number, sequence: number | null | undefined) {
  return typeof sequence === "number" ? Math.max(current, sequence) : current;
}

function cancelledStateFromTimeline(
  state: {
    threadId: string;
    messages?: AgentMessage[];
    documents?: AgentDocument[];
    observations?: AgentThreadObservation[];
    toolLogs?: ToolCallLog[];
    timelineItems?: AgentTimelineItem[];
    lastReceivedSequence?: number;
    recoveryStatus?: AgentStreamRecoveryStatus;
  },
  message: string,
  overrides?: {
    messages?: AgentMessage[];
    documents?: AgentDocument[];
    observations?: AgentThreadObservation[];
    toolLogs?: ToolCallLog[];
    timelineItems?: AgentTimelineItem[];
    lastReceivedSequence?: number;
    recoveryStatus?: AgentStreamRecoveryStatus;
  }
): ExperimentPlannerState {
  return {
    tag: "analysis_cancelled",
    threadId: state.threadId,
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

    case "AGENT_SESSION_REQUESTED":
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

    case "AGENT_SESSION_ACCEPTED":
      if (state.tag !== "starting_analysis") return state;
      return { tag: "analysis_pending", threadId: event.threadId, streamUrl: event.streamUrl, status: "PENDING", toolLogs: [] };

    case "AGENT_SESSION_FAILED":
      return { tag: "analysis_failed", message: event.message, recoverable: true };

    case "STREAM_CONNECT_REQUESTED":
      if (state.tag !== "analysis_pending") return state;
      return {
        tag: "stream_connecting",
        threadId: state.threadId,
        streamUrl: state.streamUrl,
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
        threadId: state.threadId,
        streamUrl: state.streamUrl,
        status: "ANALYZING_SIGNAL",
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
      if (event.message.sequence <= state.lastReceivedSequence) {
        return state;
      }

      const base =
        state.tag === "stream_connecting"
          ? {
              threadId: state.threadId,
              streamUrl: state.streamUrl,
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

      const text = textFromStreamMessage(event);
      const messageFromFrame: AgentMessage | null =
        text && event.message.role === "user"
          ? { message_id: event.message.id, role: "user", content: text }
          : null;
      const documents = documentsFromStreamMessage(event).reduce((nextDocuments, document) => mergeDocument(nextDocuments, document), base.documents);
      const toolLogs = toolLogsFromStreamMessage(event).reduce((nextToolLogs, toolLog) => mergeToolLog(nextToolLogs, toolLog), base.toolLogs);
      const timelineItems = mergeTimelineItems(base.timelineItems, timelineItemsFromStreamMessage(event));
      const messages = mergeMessage(base.messages, messageFromFrame);
      const observations = base.observations;
      const steps = base.steps;
      const lastReceivedSequence = nextSequence(base.lastReceivedSequence, event.message.sequence);
      const payload = payloadFromStreamMessage(event) ?? ("payload" in base ? base.payload : null);
      const approvalBlock = event.message.blocks.find((block) => block.kind === "approval");
      const resultBlock = event.message.blocks.find((block) => block.kind === "result");
      const errorBlock = event.message.blocks.find((block) => block.kind === "error");
      const signal = payload?.signals[0] ?? null;

      if (errorBlock) {
        return { tag: "analysis_failed", threadId: base.threadId, message: errorBlock.detail ?? errorBlock.title, recoverable: errorBlock.retryable ?? true };
      }

      if (approvalBlock?.kind === "approval" && payload) {
        return {
          tag: "waiting_for_approval",
          threadId: base.threadId,
          streamUrl: base.streamUrl,
          approvalId: approvalBlock.id,
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

      if (resultBlock?.kind === "result" && resultBlock.approval_result) {
        const finalExperiments = "draftExperiments" in base ? base.draftExperiments.filter((experiment) => base.selectedExperimentIds.includes(experiment.id)) : [];
        return {
          tag: "approved",
          threadId: base.threadId,
          approval: {
            ok: true,
            message: resultBlock.title,
            growth_brief_id: resultBlock.approval_result.growth_brief_id,
            created_calendar_events: resultBlock.approval_result.created_calendar_events,
            persisted_at: resultBlock.approval_result.persisted_at,
          },
          approvalResult: resultBlock.approval_result,
          calendarEvents: resultBlock.approval_result.created_calendar_events,
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

      if (signal && payload && state.tag !== "waiting_for_approval" && state.tag !== "editing_plan" && state.tag !== "approving") {
        return {
          tag: "signal_review",
          threadId: base.threadId,
          streamUrl: base.streamUrl,
          status: "GENERATING_HYPOTHESIS",
          currentStage: null,
          signal,
          payload,
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

      if (state.tag === "signal_review") {
        return {
          ...state,
          payload: payload ?? state.payload,
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

      if (state.tag !== "stream_connecting" && state.tag !== "analysis_running") {
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

      return {
        tag: "analysis_running",
        threadId: base.threadId,
        streamUrl: base.streamUrl,
        status: "SEARCHING_EVIDENCE",
        currentStage: null,
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
        threadId: state.threadId,
        streamUrl: state.streamUrl,
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

    case "STREAM_FAILED":
      return {
        tag: "analysis_failed",
        threadId: event.threadId,
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
        threadId: state.threadId,
        streamUrl: state.streamUrl,
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
        threadId: state.threadId,
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
      if (!("threadId" in state) || !state.threadId) return state;
      return cancelledStateFromTimeline({ ...state, threadId: state.threadId }, event.reason ?? "Agent session cancelled.");

    case "REJECT_SENT":
      if (!("threadId" in state) || !state.threadId) return state;
      return cancelledStateFromTimeline({ ...state, threadId: state.threadId }, event.reason ?? "Approval rejected.");

    case "RUN_CANCELLED":
      if (!("threadId" in state) || !state.threadId) return state;
      return cancelledStateFromTimeline({ ...state, threadId: state.threadId }, event.message);

    case "RESET":
      return initialExperimentPlannerState;

    default:
      return state;
  }
}

function eventFileFallback(): File {
  return new File([], "selected.csv", { type: "text/csv" });
}
