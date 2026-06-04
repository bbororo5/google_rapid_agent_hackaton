import type {
  AgentDocument,
  AgentMessage,
  AgentResultPayload,
  AgentTimelineItem,
  ExperimentItem,
  ExperimentPlannerEvent,
  ExperimentPlannerState,
  ToolCallLog,
} from "./experimentPlannerTypes";

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

function textFromStreamMessage(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }) {
  return event.message.blocks
    .filter((block) => block.kind === "text")
    .map((block) => block.text)
    .join("\n")
    .trim();
}

function documentsFromStreamMessage(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): AgentDocument[] {
  return event.message.blocks
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

function toolLogsFromStreamMessage(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): ToolCallLog[] {
  return event.message.blocks
    .filter((block) => block.kind === "activity")
    .map((block, index) => ({
      sequence: event.message.sequence * 100 + index,
      tool_name: block.id ?? block.title,
      status: block.status === "failed" ? "FAILED" : block.status === "done" ? "SUCCESS" : block.status === "running" ? "RUNNING" : "PENDING",
      duration_ms: null,
      error_message: block.status === "failed" ? block.detail ?? null : null,
    }));
}

function timelineItemsFromStreamMessage(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): AgentTimelineItem[] {
  const sequence = event.message.sequence;
  const text = textFromStreamMessage(event);
  const textItem: AgentTimelineItem[] =
    text && event.message.role === "assistant"
      ? [{ id: `message:${event.message.id}`, sequence, kind: "assistant_message", message: { message_id: event.message.id, role: "assistant", content: text } }]
      : [];
  const documentItems: AgentTimelineItem[] = documentsFromStreamMessage(event).map((document) => ({
    id: `document:${document.document_id}`,
    sequence,
    kind: "document",
    document,
  }));
  const toolItems: AgentTimelineItem[] = toolLogsFromStreamMessage(event).map((tool) => ({
    id: `tool:${tool.sequence}:${tool.tool_name}`,
    sequence,
    kind: "tool",
    tool,
  }));
  return [...textItem, ...documentItems, ...toolItems];
}

function payloadFromStreamMessage(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): AgentResultPayload | null {
  const approvalBlock = event.message.blocks.find((block) => block.kind === "approval" && block.payload);
  if (approvalBlock?.kind === "approval" && approvalBlock.payload) return approvalBlock.payload;

  const artifactBlock = event.message.blocks.find((block) => block.kind === "artifact" && isAgentResultPayload(block.content));
  if (artifactBlock?.kind === "artifact" && isAgentResultPayload(artifactBlock.content)) return artifactBlock.content;

  return null;
}

function isAgentResultPayload(value: unknown): value is AgentResultPayload {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<AgentResultPayload>;
  return Array.isArray(candidate.signals) && Array.isArray(candidate.hypotheses) && typeof candidate.experiment_plan === "object" && candidate.experiment_plan !== null;
}

export const initialExperimentPlannerState: ExperimentPlannerState = {
  phase: "idle",
  composer: {
    question: "",
    file: null,
  },
  importResult: null,
  thread: {
    threadId: null,
    streamUrl: null,
    connection: "idle",
    messages: [],
    documents: [],
    observations: [],
    toolLogs: [],
    timelineItems: [],
    lastReceivedSequence: 0,
    recoveryStatus: "idle",
  },
  review: {
    payload: null,
    activeSignalId: null,
    approvalId: null,
    selectedExperimentIds: [],
    draftExperiments: [],
    dirty: false,
    approving: false,
    approval: null,
    approvalResult: null,
    approvalSequence: null,
    calendarEvents: [],
  },
  restore: {
    parentBriefId: null,
    previousHypothesis: "",
    previousActionSummary: "",
    observedResultSummary: null,
    continuityPrompt: "",
  },
  error: null,
};

function clearError(state: ExperimentPlannerState): ExperimentPlannerState {
  return { ...state, error: null };
}

export function experimentPlannerReducer(state: ExperimentPlannerState, event: ExperimentPlannerEvent): ExperimentPlannerState {
  switch (event.type) {
    case "UPDATE_QUESTION":
      return { ...state, composer: { ...state.composer, question: event.question } };

    case "SELECT_CSV":
      return {
        ...clearError(state),
        phase: "input_ready",
        composer: { ...state.composer, file: event.file },
      };

    case "IMPORT_REQUESTED":
      if (!state.composer.file) return state;
      return { ...clearError(state), phase: "importing" };

    case "IMPORT_SUCCEEDED":
      return {
        ...clearError(state),
        phase: "input_ready",
        importResult: event.importResult,
        composer: { ...state.composer, file: null },
      };

    case "IMPORT_FAILED":
      return { ...state, phase: "import_failed", error: { message: event.message, recoverable: true } };

    case "AGENT_SESSION_REQUESTED":
      if (state.phase === "importing") return state;
      return { ...clearError(state), phase: "starting" };

    case "AGENT_SESSION_ACCEPTED":
      return {
        ...clearError(state),
        phase: "connecting",
        thread: {
          ...state.thread,
          threadId: event.threadId,
          streamUrl: event.streamUrl,
          connection: "idle",
          messages: [],
          documents: [],
          observations: [],
          toolLogs: [],
          timelineItems: [],
          lastReceivedSequence: 0,
          recoveryStatus: "idle",
        },
        review: {
          ...state.review,
          payload: null,
          activeSignalId: null,
          approvalId: null,
          selectedExperimentIds: [],
          draftExperiments: [],
          dirty: false,
          approving: false,
          approval: null,
          approvalResult: null,
          approvalSequence: null,
          calendarEvents: [],
        },
      };

    case "AGENT_SESSION_FAILED":
      return { ...state, phase: "failed", error: { message: event.message, recoverable: true } };

    case "STREAM_CONNECT_REQUESTED":
      if (!state.thread.threadId || !state.thread.streamUrl) return state;
      return {
        ...clearError(state),
        phase: "connecting",
        thread: { ...state.thread, connection: "connecting" },
      };

    case "STREAM_CONNECTED":
      return {
        ...clearError(state),
        phase: "live",
        thread: { ...state.thread, connection: "open" },
      };

    case "STREAM_EVENT_RECEIVED": {
      if (event.message.sequence <= state.thread.lastReceivedSequence) return state;

      const text = textFromStreamMessage(event);
      const messageFromFrame: AgentMessage | null =
        text && event.message.role === "user"
          ? { message_id: event.message.id, role: "user", content: text }
          : null;
      const documents = documentsFromStreamMessage(event).reduce((nextDocuments, document) => mergeDocument(nextDocuments, document), state.thread.documents);
      const toolLogs = toolLogsFromStreamMessage(event).reduce((nextToolLogs, toolLog) => mergeToolLog(nextToolLogs, toolLog), state.thread.toolLogs);
      const timelineItems = mergeTimelineItems(state.thread.timelineItems, timelineItemsFromStreamMessage(event));
      const messages = mergeMessage(state.thread.messages, messageFromFrame);
      const payload = payloadFromStreamMessage(event) ?? state.review.payload;
      const approvalBlock = event.message.blocks.find((block) => block.kind === "approval");
      const resultBlock = event.message.blocks.find((block) => block.kind === "result");
      const errorBlock = event.message.blocks.find((block) => block.kind === "error");

      const thread = {
        ...state.thread,
        connection: "open" as const,
        messages,
        documents,
        toolLogs,
        timelineItems,
        lastReceivedSequence: event.message.sequence,
      };

      if (errorBlock) {
        return {
          ...state,
          phase: "failed",
          thread,
          error: { message: errorBlock.detail ?? errorBlock.title, recoverable: errorBlock.retryable ?? true },
        };
      }

      if (resultBlock?.kind === "result" && resultBlock.approval_result) {
        const finalExperiments = state.review.draftExperiments.filter((experiment) => state.review.selectedExperimentIds.includes(experiment.id));
        return {
          ...clearError(state),
          phase: "approved",
          thread,
          review: {
            ...state.review,
            approving: false,
            approval: {
              ok: true,
              message: resultBlock.title,
              growth_brief_id: resultBlock.approval_result.growth_brief_id,
              created_calendar_events: resultBlock.approval_result.created_calendar_events,
              persisted_at: resultBlock.approval_result.persisted_at,
            },
            approvalResult: resultBlock.approval_result,
            approvalSequence: event.message.sequence,
            calendarEvents: resultBlock.approval_result.created_calendar_events,
            draftExperiments: state.review.draftExperiments.length > 0 ? state.review.draftExperiments : finalExperiments,
          },
        };
      }

      if (approvalBlock?.kind === "approval" && payload) {
        return {
          ...clearError(state),
          phase: "awaiting_approval",
          thread,
          review: {
            ...state.review,
            payload,
            activeSignalId: payload.signals[0]?.id ?? state.review.activeSignalId,
            approvalId: approvalBlock.id,
            selectedExperimentIds: payload.experiment_plan.items.map((item) => item.id),
            draftExperiments: payload.experiment_plan.items,
            dirty: false,
            approving: false,
          },
        };
      }

      if (payload && payload.signals[0] && state.phase !== "awaiting_approval" && state.phase !== "approved") {
        return {
          ...clearError(state),
          phase: "signal_review",
          thread,
          review: {
            ...state.review,
            payload,
            activeSignalId: payload.signals[0].id,
          },
        };
      }

      return {
        ...clearError(state),
        phase: state.phase === "connecting" ? "live" : state.phase,
        thread,
        review: payload ? { ...state.review, payload } : state.review,
      };
    }

    case "SIGNAL_CONFIRMED":
      if (state.phase !== "signal_review") return state;
      return { ...state, phase: "live" };

    case "STREAM_FAILED":
      return {
        ...state,
        phase: "failed",
        thread: { ...state.thread, connection: "error", threadId: event.threadId ?? state.thread.threadId },
        error: { message: event.message, recoverable: true },
      };

    case "EDIT_EXPERIMENT":
      if (state.phase !== "awaiting_approval") return state;
      return {
        ...state,
        review: {
          ...state.review,
          dirty: true,
          draftExperiments: updateDraftExperiment(state.review.draftExperiments, event.experimentId, event.patch),
        },
      };

    case "APPROVE_SENT":
      if (state.phase !== "awaiting_approval") return state;
      return {
        ...clearError(state),
        review: { ...state.review, approving: true },
      };

    case "SESSION_COMPLETED":
      return {
        ...clearError(state),
        phase: "approved",
        review: {
          ...state.review,
          approving: false,
          approval: event.approval,
          approvalResult: null,
          approvalSequence: null,
          calendarEvents: event.approval.created_calendar_events,
        },
      };

    case "APPROVE_FAILED":
      return {
        ...state,
        phase: "approval_failed",
        review: { ...state.review, approving: false },
        error: { message: event.message, recoverable: true },
      };

    case "CANCEL_SENT":
    case "REJECT_SENT":
    case "SESSION_CANCELLED":
      return {
        ...state,
        phase: "cancelled",
        thread: { ...state.thread, connection: "closed" },
        error: { message: "message" in event ? event.message : event.reason ?? "Agent session cancelled.", recoverable: true },
      };

    case "RESET":
      return initialExperimentPlannerState;

    default:
      return state;
  }
}
