import type {
  AgentDocument,
  AgentResultPayload,
  AgentTimelineItem,
  ExperimentItem,
  ExperimentPlannerEvent,
  ExperimentPlannerState,
  Hypothesis,
  Signal,
  ToolCallLog,
} from "./experimentPlannerTypes";

function updateDraftExperiment(items: ExperimentItem[], experimentId: string, patch: Partial<ExperimentItem>) {
  return items.map((item) => (item.id === experimentId ? { ...item, ...patch } : item));
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
      display_title: block.title,
      display_detail: block.detail ?? null,
      status: block.status === "failed" ? "FAILED" : block.status === "done" ? "SUCCESS" : block.status === "running" ? "RUNNING" : "PENDING",
      duration_ms: null,
      error_message: block.status === "failed" ? block.detail ?? null : null,
    }));
}

function timelineItemsFromStreamMessage(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }): AgentTimelineItem[] {
  const sequence = event.message.sequence;
  return event.message.blocks.flatMap((block, index): AgentTimelineItem[] => {
    const itemSequence = sequence + index / 1000;
    if (block.kind === "text") {
      const text = block.text.trim();
      if (!text) return [];
      return event.message.role === "user"
        ? [{ id: `message:${event.message.id}:${index}`, sequence: itemSequence, kind: "user_message", message: { message_id: event.message.id, role: "user", content: text } }]
        : [{ id: `message:${event.message.id}:${index}`, sequence: itemSequence, kind: "assistant_message", message: { message_id: event.message.id, role: "assistant", content: text } }];
    }

    if (block.kind === "markdown_document") {
      const document: AgentDocument = {
        document_id: block.id,
        kind: block.id.includes("evidence_scan") ? "evidence_scan" : "generic",
        title: block.title,
        format: "markdown",
        summary: block.summary ?? block.title,
        content: block.markdown,
      };
      return [{ id: `document:${document.document_id}`, sequence: itemSequence, kind: "document", document }];
    }

    if (block.kind === "artifact") {
      return [
        {
          id: `artifact:${block.id}`,
          sequence: itemSequence,
          kind: "artifact",
          artifactKind: block.artifact_kind,
          title: block.title,
          content: block.content,
        },
      ];
    }

    if (block.kind !== "activity") return [];
    const tool: ToolCallLog = {
      sequence: event.message.sequence * 100 + index,
      tool_name: block.id ?? block.title,
      display_title: block.title,
      display_detail: block.detail ?? null,
      status: block.status === "failed" ? "FAILED" : block.status === "done" ? "SUCCESS" : block.status === "running" ? "RUNNING" : "PENDING",
      duration_ms: null,
      error_message: block.status === "failed" ? block.detail ?? null : null,
    };
    return [{ id: `tool:${tool.sequence}:${tool.tool_name}`, sequence: itemSequence, kind: "tool", tool }];
  });
}

function payloadFromStreamMessage(event: ExperimentPlannerEvent & { type: "STREAM_EVENT_RECEIVED" }, currentPayload: AgentResultPayload | null): AgentResultPayload | null {
  const approvalBlock = event.message.blocks.find((block) => block.kind === "approval" && block.payload);
  if (approvalBlock?.kind === "approval" && approvalBlock.payload) return approvalBlock.payload;

  const artifactBlock = event.message.blocks.find((block) => block.kind === "artifact" && isAgentResultPayload(block.content));
  if (artifactBlock?.kind === "artifact" && isAgentResultPayload(artifactBlock.content)) return mergeAgentResultPayload(currentPayload, artifactBlock.content);

  const signalArtifact = event.message.blocks.find((block) => block.kind === "artifact" && signalsFromArtifactContent(block.content).length > 0);
  if (signalArtifact?.kind === "artifact") {
    const signals = signalsFromArtifactContent(signalArtifact.content);
    return mergeAgentResultPayload(currentPayload, {
      signals,
      hypotheses: [],
      experiment_plan: currentPayload?.experiment_plan ?? {
        id: `plan_pending:${signals[0].id}`,
        summary: "",
        overall_confidence: signals[0].confidence,
        items: [],
      },
    });
  }

  const hypothesisArtifact = event.message.blocks.find((block) => block.kind === "artifact" && hypothesesFromArtifactContent(block.content).length > 0);
  if (hypothesisArtifact?.kind === "artifact") {
    return mergeAgentResultPayload(currentPayload, {
      signals: [],
      hypotheses: hypothesesFromArtifactContent(hypothesisArtifact.content),
      experiment_plan: currentPayload?.experiment_plan ?? {
        id: "plan_pending",
        summary: "",
        overall_confidence: "medium",
        items: [],
      },
    });
  }

  return null;
}

function mergeById<T extends { id: string }>(previous: T[], next: T[]) {
  const merged = new Map(previous.map((item) => [item.id, item]));
  next.forEach((item) => merged.set(item.id, { ...merged.get(item.id), ...item }));
  return [...merged.values()];
}

function mergeAgentResultPayload(current: AgentResultPayload | null, next: AgentResultPayload): AgentResultPayload {
  return {
    signals: mergeById(current?.signals ?? [], next.signals),
    hypotheses: mergeById(current?.hypotheses ?? [], next.hypotheses),
    experiment_plan: next.experiment_plan.items.length > 0 || !current?.experiment_plan ? next.experiment_plan : current.experiment_plan,
  };
}

function isAgentResultPayload(value: unknown): value is AgentResultPayload {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<AgentResultPayload>;
  return Array.isArray(candidate.signals) && Array.isArray(candidate.hypotheses) && typeof candidate.experiment_plan === "object" && candidate.experiment_plan !== null;
}

function isSignal(value: unknown): value is Signal {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Signal>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.title === "string" &&
    typeof candidate.description === "string" &&
    typeof candidate.metric_name === "string" &&
    typeof candidate.current_value === "number" &&
    typeof candidate.baseline_value === "number" &&
    typeof candidate.lift_ratio === "number" &&
    typeof candidate.confidence === "string" &&
    Array.isArray(candidate.evidence_refs)
  );
}

function isHypothesis(value: unknown): value is Hypothesis {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Hypothesis>;
  return typeof candidate.id === "string" && Array.isArray(candidate.signal_ids) && typeof candidate.statement === "string";
}

function signalsFromArtifactContent(content: unknown): Signal[] {
  if (isSignal(content)) return [content];
  if (!content || typeof content !== "object") return [];
  const candidate = content as { signals?: unknown };
  return Array.isArray(candidate.signals) ? candidate.signals.filter(isSignal) : [];
}

function hypothesesFromArtifactContent(content: unknown): Hypothesis[] {
  if (isHypothesis(content)) return [content];
  if (!content || typeof content !== "object") return [];
  const candidate = content as { hypotheses?: unknown };
  return Array.isArray(candidate.hypotheses) ? candidate.hypotheses.filter(isHypothesis) : [];
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
    receivedMessageIds: [],
    lastReceivedSequence: 0,
    recoveryStatus: "idle",
  },
  review: {
    payload: null,
    activeSignalId: null,
    approvalId: null,
    selectedHypothesisId: null,
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
        phase: state.thread.threadId ? state.phase : "input_ready",
        composer: { ...state.composer, file: event.file },
      };

    case "CLEAR_SELECTED_CSV":
      return {
        ...state,
        composer: { ...state.composer, file: null },
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
          receivedMessageIds: [],
          lastReceivedSequence: 0,
          recoveryStatus: "idle",
        },
        review: {
          ...state.review,
          payload: null,
          activeSignalId: null,
          approvalId: null,
          selectedHypothesisId: null,
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
      if (state.thread.receivedMessageIds.includes(event.message.id)) return state;

      const documents = documentsFromStreamMessage(event).reduce((nextDocuments, document) => mergeDocument(nextDocuments, document), state.thread.documents);
      const toolLogs = toolLogsFromStreamMessage(event).reduce((nextToolLogs, toolLog) => mergeToolLog(nextToolLogs, toolLog), state.thread.toolLogs);
      const timelineItems = mergeTimelineItems(state.thread.timelineItems, timelineItemsFromStreamMessage(event));
      // Server-echoed user text now flows through timelineItems (kind user_message)
      // so it keeps its real stream sequence and interleaves with assistant blocks.
      const messages = state.thread.messages;
      const payload = payloadFromStreamMessage(event, state.review.payload) ?? state.review.payload;
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
        receivedMessageIds: [...state.thread.receivedMessageIds, event.message.id],
        lastReceivedSequence: Math.max(state.thread.lastReceivedSequence, event.message.sequence),
      };

      if (errorBlock) {
        return {
          ...state,
          phase: state.review.approving ? "awaiting_approval" : "failed",
          thread,
          review: { ...state.review, approving: false },
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
            selectedHypothesisId: null,
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

    case "TOGGLE_EXPERIMENT": {
      if (state.phase !== "awaiting_approval") return state;
      const selected = state.review.selectedExperimentIds.includes(event.experimentId)
        ? state.review.selectedExperimentIds.filter((id) => id !== event.experimentId)
        : [...state.review.selectedExperimentIds, event.experimentId];
      // Manually toggling an experiment leaves the "single hypothesis" filter mode.
      return { ...state, review: { ...state.review, dirty: true, selectedHypothesisId: null, selectedExperimentIds: selected } };
    }

    case "SELECT_HYPOTHESIS": {
      if (state.phase !== "awaiting_approval") return state;
      // Visual filter (option A): toggling a hypothesis scopes the approved set to
      // that hypothesis's experiments. Re-selecting it clears back to all.
      const clearing = state.review.selectedHypothesisId === event.hypothesisId;
      const items = state.review.draftExperiments;
      const selected = clearing
        ? items.map((item) => item.id)
        : items.filter((item) => item.hypothesis_id === event.hypothesisId).map((item) => item.id);
      return {
        ...state,
        review: {
          ...state.review,
          dirty: true,
          selectedHypothesisId: clearing ? null : event.hypothesisId,
          selectedExperimentIds: selected,
        },
      };
    }

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
