"use client";

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { createWebSocketAgentStreamApi, type AgentStreamConnection, type AgentStreamApi } from "../api/agentStreamApi";
import { createFetchExperimentPlannerApi, type ExperimentPlannerApi } from "../api/experimentPlannerApi";
import { buildAgentRunRequest, buildApprovalRequest } from "../state/experimentPlannerRequests";
import { initialExperimentPlannerState, experimentPlannerReducer } from "../state/experimentPlannerReducer";
import type {
  ApproveExperimentPlanResponse,
  CalendarEventRef,
  ExperimentItem,
  AgentDocument,
  AgentObservation,
  AgentMessage,
  AgentStreamRecoveryStatus,
  AgentRunStage,
  AgentTimelineItem,
  Hypothesis,
  Signal,
  ToolCallLog,
  ExperimentPlannerState,
  ImportCsvResponse,
} from "../state/experimentPlannerTypes";

export interface ChecklistStep {
  label: string;
  status: "complete" | "active" | "pending";
}

type AgentDisplayState = "idle" | "selected" | "importing" | "processing" | "ready" | "approved" | "error";

export type GateReview =
  | {
      id: "signal";
      title: "Signal Review";
      status: "active" | "complete";
      signal: Signal;
      actionLabel: string;
    }
  | {
      id: "approval";
      title: "Experiment Approval";
      status: "active" | "complete";
      hypothesis: Hypothesis | null;
      experiment: ExperimentItem | null;
      actionLabel: string;
    };

export interface StatusRow {
  title: string;
  detail: string;
}

export type PlannerScreenMode =
  | "empty"
  | "input_ready"
  | "importing"
  | "starting_run"
  | "connecting_stream"
  | "live_run"
  | "signal_review"
  | "plan_review"
  | "approved_summary"
  | "error";

export interface PlannerShellView {
  campaignName: string;
  campaignStatus: "active" | "needs_review" | "approved" | "error";
}

export interface PlannerScreenView {
  mode: PlannerScreenMode;
  intro: { title: string; description: string } | null;
  statusRows: StatusRow[];
  errorMessage: string | null;
}

export type ComposerMode = "prepare_run" | "run_in_progress" | "review_gate" | "approval_gate" | "completed" | "error";

export type ComposerPrimaryAction =
  | { kind: "analyze"; label: "Send"; disabled: boolean; title?: string }
  | { kind: "send"; label: "Send"; disabled: boolean; title?: string }
  | { kind: "stop"; label: "Stop"; disabled: boolean; title?: string }
  | { kind: "retry"; label: "Retry"; disabled: boolean; title?: string }
  | { kind: "new_run"; label: "Run new"; disabled: boolean; title?: string }
  | { kind: "none" };

export interface PlannerComposerView {
  mode: ComposerMode;
  value: string;
  placeholder: string;
  inputDisabled: boolean;
  fileName: string | null;
  canAttachCsv: boolean;
  primaryAction: ComposerPrimaryAction;
}

export interface PlannerProgressView {
  visible: boolean;
  runLabel: string | null;
  stateLabel: string;
  steps: ChecklistStep[];
}

export type StreamMessageBlock =
  | { kind: "text"; text: string }
  | { kind: "activity"; id: string; title: string; status: "queued" | "running" | "done" | "failed"; detail?: string }
  | { kind: "markdown_document"; id: string; title: string; summary?: string; markdown: string; document: AgentDocument }
  | { kind: "artifact"; id: string; artifactKind: "signal" | "hypothesis" | "experiment_plan" | "growth_brief"; title: string; content: unknown }
  | { kind: "approval"; id: string; title: string; targetId: string; actions: ("approve" | "reject" | "request_changes")[] }
  | { kind: "result"; title: string; detail?: string }
  | { kind: "error"; title: string; detail?: string; retryable?: boolean };

export interface StreamMessage {
  id: string;
  sequence: number;
  role: "user" | "assistant" | "system";
  createdAt: string | null;
  blocks: StreamMessageBlock[];
}

export interface PlannerThreadView {
  hasActivity: boolean;
  streamMessages: StreamMessage[];
  userMessages: AgentMessage[];
  assistantMessages: AgentMessage[];
  documents: AgentDocument[];
  observations: AgentObservation[];
  toolLogs: ToolCallLog[];
  timelineItems: AgentTimelineItem[];
  primaryExperiment: ExperimentItem | null;
}

export interface PlannerInspectorView {
  canToggle: boolean;
  activeGateKey: string | null;
  currentGate: GateReview | null;
  history: GateReview[];
}

export interface PlannerApprovalView {
  canApprove: boolean;
  isApproving: boolean;
  draftExperiments: ExperimentItem[];
  finalExperiments: ExperimentItem[];
  primaryExperiment: ExperimentItem | null;
  receipt: ApproveExperimentPlanResponse | null;
  calendarEvents: CalendarEventRef[];
}

export interface ExperimentPlannerViewModel {
  shell: PlannerShellView;
  screen: PlannerScreenView;
  composer: PlannerComposerView;
  progress: PlannerProgressView;
  thread: PlannerThreadView;
  inspector: PlannerInspectorView;
  approval: PlannerApprovalView;
  importResult: ImportCsvResponse | null;
  signals: Signal[];
  hypotheses: Hypothesis[];
  toolLogs: ToolCallLog[];
  streamRecoveryStatus: AgentStreamRecoveryStatus;
  commands: {
    selectCsv: (file: File) => void;
    updateQuestion: (question: string) => void;
    sendMessage: () => void;
    analyze: () => Promise<void>;
    continueSignalReview: () => void;
    editExperiment: (experimentId: string, title: string) => void;
    approve: () => Promise<void>;
    reject: (reason?: string) => void;
    cancel: (reason?: string) => Promise<void>;
    reset: () => void;
  };
}

function stateMessage(state: ExperimentPlannerState) {
  return "message" in state ? state.message : null;
}

function stateFile(state: ExperimentPlannerState) {
  return "file" in state ? state.file ?? null : null;
}

function stateQuestion(state: ExperimentPlannerState) {
  return "question" in state ? state.question : "";
}

function payloadSignals(state: ExperimentPlannerState) {
  return "payload" in state ? state.payload.signals : [];
}

function payloadHypotheses(state: ExperimentPlannerState) {
  return "payload" in state ? state.payload.hypotheses : [];
}

function draftExperiments(state: ExperimentPlannerState) {
  return "draftExperiments" in state ? state.draftExperiments : [];
}

function finalExperiments(state: ExperimentPlannerState) {
  return "finalExperiments" in state ? state.finalExperiments : [];
}

function messages(state: ExperimentPlannerState) {
  return "messages" in state ? state.messages : [];
}

function documents(state: ExperimentPlannerState) {
  return "documents" in state ? state.documents : [];
}

function toolLogs(state: ExperimentPlannerState) {
  return "toolLogs" in state ? state.toolLogs : [];
}

function observations(state: ExperimentPlannerState) {
  return "observations" in state ? state.observations : [];
}

function timelineItems(state: ExperimentPlannerState) {
  return "timelineItems" in state ? state.timelineItems : [];
}

function approval(state: ExperimentPlannerState) {
  return "approval" in state ? state.approval : null;
}

function calendarEvents(state: ExperimentPlannerState) {
  return "calendarEvents" in state ? state.calendarEvents : [];
}

function lastReceivedSequence(state: ExperimentPlannerState) {
  return "lastReceivedSequence" in state ? state.lastReceivedSequence : 0;
}

function streamRecoveryStatus(state: ExperimentPlannerState): AgentStreamRecoveryStatus {
  return "recoveryStatus" in state ? state.recoveryStatus : "idle";
}

function stateImportResult(state: ExperimentPlannerState) {
  return "importResult" in state ? state.importResult : null;
}

function commandId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "_")}`;
}

function toolBlock(tool: ToolCallLog): StreamMessageBlock {
  const status = tool.status === "FAILED" ? "failed" : tool.status === "SUCCESS" ? "done" : tool.status === "RUNNING" ? "running" : "queued";
  return {
    kind: "activity",
    id: `tool:${tool.sequence}:${tool.tool_name}`,
    title: toolStatusLabel(tool),
    status,
    detail: tool.error_message ?? undefined,
  };
}

function toolStatusLabel(tool: ToolCallLog) {
  const labels: Record<string, string> = {
    query_metric_baseline: "metric baseline",
    search_content_posts: "supporting posts",
    search_team_notes: "team context",
  };
  const displayName =
    labels[tool.tool_name] ??
    tool.tool_name
      .split("_")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");

  if (tool.status === "FAILED" && tool.error_message) return `Could not check ${displayName}: ${tool.error_message}`;
  if (tool.status === "FAILED") return `Could not check ${displayName}`;
  if (tool.status === "SUCCESS" && tool.duration_ms !== null) return `Checked ${displayName} in ${tool.duration_ms}ms`;
  if (tool.status === "SUCCESS") return `Checked ${displayName}`;
  if (tool.status === "RUNNING") return `Checking ${displayName}`;
  return `Queued ${displayName}`;
}

function streamMessagesFromState(input: {
  messages: AgentMessage[];
  timelineItems: AgentTimelineItem[];
  primaryExperiment: ExperimentItem | null;
  approval: ApproveExperimentPlanResponse | null;
  calendarEvents: CalendarEventRef[];
  errorMessage: string | null;
  stateLabel: string;
}): StreamMessage[] {
  const initialUserMessages = input.messages.filter((message) => message.role === "user" && !message.message_id.startsWith("msg_local_"));
  const localUserMessages = input.messages.filter((message) => message.role === "user" && message.message_id.startsWith("msg_local_"));
  const assistantMessages = input.messages.filter((message) => message.role === "assistant");
  const streamMessages: StreamMessage[] = [
    ...initialUserMessages.map((message, index) => ({
      id: message.message_id,
      sequence: index + 1,
      role: "user" as const,
      createdAt: null,
      blocks: [{ kind: "text" as const, text: message.content }],
    })),
    ...assistantMessages.map((message, index) => ({
      id: message.message_id,
      sequence: 100 + index,
      role: "assistant" as const,
      createdAt: null,
      blocks: [{ kind: "text" as const, text: message.content }],
    })),
    ...input.timelineItems.map((item) => {
      if (item.kind === "tool") {
        return {
          id: item.id,
          sequence: item.sequence,
          role: "assistant" as const,
          createdAt: null,
          blocks: [toolBlock(item.tool)],
        };
      }
      if (item.kind === "document") {
        return {
          id: item.id,
          sequence: item.sequence,
          role: "assistant" as const,
          createdAt: null,
          blocks: [
            {
              kind: "markdown_document" as const,
              id: item.document.document_id,
              title: item.document.title,
              summary: item.document.summary,
              markdown: item.document.content,
              document: item.document,
            },
          ],
        };
      }
      if (item.kind === "observation") {
        return {
          id: item.id,
          sequence: item.sequence,
          role: "assistant" as const,
          createdAt: null,
          blocks: [{ kind: "text" as const, text: item.observation.summary }],
        };
      }
      return {
        id: item.id,
        sequence: item.sequence,
        role: "assistant" as const,
        createdAt: null,
        blocks: [{ kind: "text" as const, text: item.message.content }],
      };
    }),
    ...localUserMessages.map((message, index) => ({
      id: message.message_id,
      sequence: 10_000 + index,
      role: "user" as const,
      createdAt: null,
      blocks: [{ kind: "text" as const, text: message.content }],
    })),
  ];

  if (input.primaryExperiment) {
    streamMessages.push({
      id: `artifact:${input.primaryExperiment.id}`,
      sequence: 20_000,
      role: "assistant",
      createdAt: null,
      blocks: [
        {
          kind: "artifact",
          id: input.primaryExperiment.id,
          artifactKind: "experiment_plan",
          title: input.primaryExperiment.title,
          content: input.primaryExperiment,
        },
      ],
    });
  }

  if (input.approval) {
    streamMessages.push({
      id: `result:${input.approval.growth_brief_id}`,
      sequence: 20_100,
      role: "assistant",
      createdAt: null,
      blocks: [
        {
          kind: "result",
          title: "Approval complete",
          detail: `Growth brief ${input.approval.growth_brief_id} and ${input.calendarEvents.length} calendar event${input.calendarEvents.length === 1 ? "" : "s"} are ready.`,
        },
      ],
    });
  }

  if (input.errorMessage) {
    streamMessages.push({
      id: `error:${input.errorMessage}`,
      sequence: 30_000,
      role: "system",
      createdAt: null,
      blocks: [{ kind: "error", title: `Agent run · ${input.stateLabel}`, detail: input.errorMessage, retryable: true }],
    });
  }

  return streamMessages.sort((a, b) => a.sequence - b.sequence);
}

function stateSignal(state: ExperimentPlannerState) {
  if (state.tag === "signal_review") return state.signal;
  return payloadSignals(state)[0] ?? null;
}

function buildChecklist(state: ExperimentPlannerState): ChecklistStep[] {
  const complete = "complete" as const;
  const active = "active" as const;
  const pending = "pending" as const;
  const pendingRunSteps: ChecklistStep[] = [
    { label: "Import metrics", status: pending },
    { label: "Start agent run", status: pending },
    { label: "Connect stream", status: pending },
    { label: "Analyze signal", status: pending },
    { label: "Draft experiment plan", status: pending },
    { label: "Review experiment plan", status: pending },
  ];

  if ("steps" in state && state.steps.length > 0) {
    const streamSteps = state.steps.map((step) => ({
      label: stageLabel(step.stage),
      status: step.status === "SUCCEEDED" ? complete : step.status === "IN_PROGRESS" ? active : pending,
    }));
    const hasImportStep = streamSteps.some((step) => step.label === "Import metrics");

    return [
      ...(hasImportStep ? [] : [{ label: "Import metrics", status: complete }]),
      { label: "Start agent run", status: complete },
      { label: "Connect stream", status: complete },
      ...streamSteps,
    ];
  }

  if (state.tag === "idle" || state.tag === "csv_selected") {
    return pendingRunSteps;
  }

  if (state.tag === "importing_csv" || state.tag === "import_succeeded") {
    return [
      { label: "Import metrics", status: state.tag === "importing_csv" ? active : complete },
      { label: "Start agent run", status: state.tag === "import_succeeded" ? active : pending },
      { label: "Connect stream", status: pending },
      { label: "Analyze signal", status: pending },
      { label: "Draft experiment plan", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "starting_analysis") {
    return [
      { label: "Import metrics", status: complete },
      { label: "Start agent run", status: active },
      { label: "Connect stream", status: pending },
      { label: "Analyze signal", status: pending },
      { label: "Draft experiment plan", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "analysis_pending" || state.tag === "stream_connecting") {
    return [
      { label: "Import metrics", status: complete },
      { label: "Start agent run", status: complete },
      { label: "Connect stream", status: active },
      { label: "Analyze signal", status: pending },
      { label: "Draft experiment plan", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "analysis_running") {
    return [
      { label: "Import metrics", status: complete },
      { label: "Start agent run", status: complete },
      { label: "Connect stream", status: complete },
      { label: "Analyze signal", status: active },
      { label: "Draft experiment plan", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "waiting_for_approval" || state.tag === "editing_plan" || state.tag === "approving" || state.tag === "approved") {
    return [
      { label: "Import metrics", status: complete },
      { label: "Start agent run", status: complete },
      { label: "Connect stream", status: complete },
      { label: "Analyze signal", status: complete },
      { label: "Draft experiment plan", status: complete },
      { label: "Review experiment plan", status: state.tag === "approved" ? complete : active },
    ];
  }

  return pendingRunSteps;
}

function stageLabel(stage: AgentRunStage) {
  switch (stage) {
    case "IMPORT_METRICS":
      return "Import metrics";
    case "DETECT_PERFORMANCE_SIGNAL":
      return "Analyze signal";
    case "GROUND_WITH_EVIDENCE":
      return "Ground with evidence";
    case "GENERATE_HYPOTHESIS":
      return "Generate hypotheses";
    case "DRAFT_EXPERIMENT_PLAN":
      return "Draft experiment plan";
    case "WAIT_FOR_APPROVAL":
      return "Review experiment plan";
    case "APPLY_APPROVED_PLAN":
      return "Create brief and calendar";
    default:
      return "Agent step";
  }
}

function agentState(state: ExperimentPlannerState): AgentDisplayState {
  if (state.tag === "csv_selected") return "selected";
  if (state.tag === "importing_csv") return "importing";
  if (state.tag === "signal_review") return "ready";
  if (state.tag === "import_succeeded") return "processing";
  if (state.tag === "starting_analysis" || state.tag === "analysis_pending" || state.tag === "stream_connecting" || state.tag === "analysis_running") return "processing";
  if (state.tag === "waiting_for_approval" || state.tag === "editing_plan" || state.tag === "approving") return "ready";
  if (state.tag === "approved") return "approved";
  if (state.tag === "analysis_failed" || state.tag === "approval_failed" || state.tag === "import_failed") return "error";
  return "idle";
}

function runShortId(state: ExperimentPlannerState) {
  return "agentRunId" in state && state.agentRunId ? state.agentRunId.slice(-3) : null;
}

function readableWorkflowState(state: ExperimentPlannerState, displayState: AgentDisplayState) {
  switch (state.tag) {
    case "import_succeeded":
    case "starting_analysis":
      return "Starting run";
    case "analysis_pending":
      return "Run accepted";
    case "stream_connecting":
      return "Connecting stream";
    case "analysis_running":
      return "Analyzing signal";
    default:
      break;
  }

  switch (displayState) {
    case "selected":
      return "Ready to analyze";
    case "importing":
      return "Importing metrics";
    case "processing":
      return "Analyzing";
    case "ready":
      return "Review needed";
    case "approved":
      return "Approved";
    case "error":
      return "Needs attention";
    default:
      return "Waiting for evidence";
  }
}

function screenMode(state: ExperimentPlannerState, displayState: AgentDisplayState): PlannerScreenMode {
  if (state.tag === "idle") return "empty";
  if (state.tag === "csv_selected") return "input_ready";
  if (state.tag === "importing_csv") return "importing";
  if (state.tag === "import_succeeded" || state.tag === "starting_analysis" || state.tag === "analysis_pending") return "starting_run";
  if (state.tag === "stream_connecting") return "connecting_stream";
  if (state.tag === "analysis_running") return "live_run";
  if (state.tag === "signal_review") return "signal_review";
  if (state.tag === "waiting_for_approval" || state.tag === "editing_plan" || state.tag === "approving") return "plan_review";
  if (state.tag === "approved") return "approved_summary";
  if (displayState === "error") return "error";
  return "live_run";
}

function composerFromState(state: ExperimentPlannerState, displayState: AgentDisplayState, value: string, fileName: string | null): PlannerComposerView {
  const base = {
    value,
    fileName,
    placeholder: "Add context or instructions for the agent...",
  };

  switch (state.tag) {
    case "idle":
      return {
        ...base,
        mode: "prepare_run",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: {
          kind: "send",
          label: "Send",
          disabled: !value.trim(),
          title: "Send a message to the thread, or attach campaign metrics CSV to start analysis",
        },
      };
    case "csv_selected":
    case "import_succeeded":
      return {
        ...base,
        mode: "prepare_run",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: {
          kind: "analyze",
          label: "Send",
          disabled: !value.trim() && !fileName,
          title: fileName ? "Send instructions and start analysis" : "Attach campaign metrics CSV to start analysis, or send a message to the thread",
        },
      };
    case "import_failed":
      return {
        ...base,
        mode: "error",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: {
          kind: "retry",
          label: "Retry",
          disabled: !fileName,
          title: fileName ? undefined : "Attach campaign metrics CSV to enable Analyze",
        },
      };
    case "importing_csv":
    case "starting_analysis":
    case "analysis_pending":
    case "stream_connecting":
    case "analysis_running":
      return {
        ...base,
        mode: "run_in_progress",
        inputDisabled: false,
        canAttachCsv: false,
        primaryAction: {
          kind: "stop",
          label: "Stop",
          disabled: !("agentRunId" in state),
          title: "Stop this analysis run",
        },
      };
    case "signal_review":
      return {
        ...base,
        mode: "review_gate",
        inputDisabled: false,
        canAttachCsv: false,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim(), title: "Send a message to the thread" },
      };
    case "waiting_for_approval":
    case "editing_plan":
    case "approving":
      return {
        ...base,
        mode: "approval_gate",
        inputDisabled: false,
        canAttachCsv: false,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim(), title: "Send a message to the thread" },
      };
    case "approved":
      return {
        ...base,
        mode: "completed",
        inputDisabled: false,
        canAttachCsv: false,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim(), title: "Send a message to the thread" },
      };
    case "analysis_failed":
    case "analysis_cancelled":
      return {
        ...base,
        mode: "error",
        inputDisabled: false,
        canAttachCsv: false,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim(), title: "Send a message to the thread" },
      };
    default:
      return {
        ...base,
        mode: displayState === "processing" ? "run_in_progress" : "prepare_run",
        inputDisabled: false,
        canAttachCsv: displayState !== "processing",
        primaryAction: displayState === "processing" ? { kind: "stop", label: "Stop", disabled: true } : { kind: "send", label: "Send", disabled: !value.trim() },
      };
  }
}

function buildStatusRows(state: ExperimentPlannerState, importResult: ImportCsvResponse | null, hasLiveThreadActivity: boolean): StatusRow[] {
  switch (state.tag) {
    case "importing_csv":
      return [{ title: "Importing campaign metrics...", detail: "Preparing the evidence store before signal detection." }];
    case "import_succeeded":
    case "starting_analysis":
      return [
        {
          title: "Starting the analysis run...",
          detail: importResult ? `${importResult.indexed_count} rows indexed · ${importResult.failed_count} failed` : "Campaign metrics are indexed.",
        },
      ];
    case "analysis_pending":
      return [{ title: "Agent run accepted.", detail: "Opening the live agent stream." }];
    case "stream_connecting":
      return [{ title: "Connecting live agent stream...", detail: "Signal and evidence events will appear here as they arrive." }];
    case "analysis_running":
      return hasLiveThreadActivity ? [] : [{ title: "Listening for agent events...", detail: "The stream is open and waiting for the first signal update." }];
    default:
      return [];
  }
}

export function useExperimentPlannerController(apiOverride?: ExperimentPlannerApi, streamOverride?: AgentStreamApi): ExperimentPlannerViewModel {
  const [state, dispatch] = useReducer(experimentPlannerReducer, initialExperimentPlannerState);
  const [composerQuestion, setComposerQuestion] = useState(stateQuestion(initialExperimentPlannerState));
  const [localUserMessages, setLocalUserMessages] = useState<AgentMessage[]>([]);
  const [isApproving, setIsApproving] = useState(false);
  const stateRef = useRef(state);
  const composerQuestionRef = useRef(composerQuestion);
  const streamRef = useRef<AgentStreamConnection | null>(null);
  const lastFileRef = useRef<File | null>(null);
  const lastImportRef = useRef<ImportCsvResponse | null>(null);
  const lastSignalRef = useRef<Signal | null>(null);
  const lastSignalsRef = useRef<Signal[]>([]);
  const lastHypothesesRef = useRef<Hypothesis[]>([]);
  const api = useMemo(() => apiOverride ?? createFetchExperimentPlannerApi(), [apiOverride]);
  const streamApi = useMemo(() => streamOverride ?? createWebSocketAgentStreamApi(), [streamOverride]);
  stateRef.current = state;
  composerQuestionRef.current = composerQuestion;

  useEffect(() => {
    return () => {
      streamRef.current?.close();
    };
  }, []);

  const currentFile = stateFile(state);
  const currentQuestion = composerQuestion;
  if (currentFile) {
    lastFileRef.current = currentFile;
  }

  const currentImportResult = stateImportResult(state);
  if (currentImportResult) {
    lastImportRef.current = currentImportResult;
  }

  const currentSignals = payloadSignals(state);
  if (currentSignals.length > 0) {
    lastSignalsRef.current = currentSignals;
    lastSignalRef.current = currentSignals[0];
  }

  const currentHypotheses = payloadHypotheses(state);
  if (currentHypotheses.length > 0) {
    lastHypothesesRef.current = currentHypotheses;
  }

  const currentSignal = stateSignal(state);
  if (currentSignal) {
    lastSignalRef.current = currentSignal;
  }

  async function connectStream(agentRunId: string, streamUrl: string) {
    streamRef.current?.close();
    dispatch({ type: "STREAM_CONNECT_REQUESTED" });

    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const settle = (callback: () => void) => {
        if (settled) return;
        settled = true;
        callback();
      };

      streamRef.current = streamApi.connect({
        agentRunId,
        streamUrl,
        onOpen: () => dispatch({ type: "STREAM_CONNECTED" }),
        getLastReceivedSequence: () => lastReceivedSequence(stateRef.current),
        onEvent: (streamEvent) => {
          dispatch({ type: "STREAM_EVENT_RECEIVED", event: streamEvent });
          if (streamEvent.type === "approval.requested" || streamEvent.type === "approval.committed" || streamEvent.type === "run.completed") {
            settle(resolve);
          }
          if (streamEvent.type === "run.failed") {
            settle(() => reject(new Error(streamEvent.error_message ?? "Agent run failed.")));
          }
        },
        onError: (message) => {
          dispatch({ type: "STREAM_FAILED", agentRunId, message });
          settle(() => reject(new Error(message)));
        },
      });
    });
  }

  async function analyze() {
    const current = stateRef.current;
    if (current.tag !== "csv_selected") return;
    let phase: "import" | "analysis" = "import";

    try {
      const importingState = experimentPlannerReducer(current, { type: "IMPORT_REQUESTED" });
      dispatch({ type: "IMPORT_REQUESTED" });
      if (importingState.tag !== "importing_csv") return;

      const importResult = await api.importCsv({
        file: current.file,
        workspaceId: "demo_workspace",
        campaignId: "camp_comeback_teaser",
      });
      lastImportRef.current = importResult;
      phase = "analysis";

      const importedState = experimentPlannerReducer(importingState, { type: "IMPORT_SUCCEEDED", importResult });
      dispatch({ type: "IMPORT_SUCCEEDED", importResult });
      if (importedState.tag !== "import_succeeded") return;

      const startingState = experimentPlannerReducer(
        { ...importedState, question: composerQuestionRef.current },
        { type: "RUN_AGENT_REQUESTED" },
      );
      dispatch({ type: "RUN_AGENT_REQUESTED" });
      if (startingState.tag !== "starting_analysis") return;

      const accepted = await api.runAgent(buildAgentRunRequest(startingState.source));
      dispatch({
        type: "RUN_AGENT_ACCEPTED",
        agentRunId: accepted.agent_run_id,
        streamUrl: accepted.stream_url,
        snapshotUrl: accepted.next_poll_url,
      });
      await connectStream(accepted.agent_run_id, accepted.stream_url);
    } catch (error) {
      dispatch({
        type: phase === "import" ? "IMPORT_FAILED" : "RUN_AGENT_FAILED",
        message: error instanceof Error ? error.message : phase === "import" ? "Import failed." : "Analysis failed.",
      });
    }
  }

  function sendComposerMessage() {
    const text = composerQuestionRef.current.trim();
    const current = stateRef.current;

    if (current.tag === "csv_selected") {
      void analyze();
      return;
    }

    if (!text) return;

    if ("agentRunId" in current && current.agentRunId) {
      streamRef.current?.send({
        command_id: commandId("cmd_message"),
        type: "message.send",
        agent_run_id: current.agentRunId,
        content: text,
        client_created_at: new Date().toISOString(),
      } as never);
    }

    setLocalUserMessages((messages) => [
      ...messages,
      {
        message_id: `msg_local_${Date.now()}`,
        role: "user",
        content: text,
      },
    ]);
    composerQuestionRef.current = "";
    setComposerQuestion("");
    dispatch({ type: "UPDATE_QUESTION", question: "" });
  }

  function continueSignalReview() {
    const current = stateRef.current;
    if (current.tag !== "signal_review") return;
    dispatch({ type: "SIGNAL_CONFIRMED" });
    streamRef.current?.send({
      command_id: commandId("cmd_continue"),
      type: "run.continue",
      agent_run_id: current.agentRunId,
      approval_id: null,
      final_experiments: null,
      reason: "signal.accepted",
    });
  }

  async function approvePlan() {
    const current = stateRef.current;
    if (current.tag !== "waiting_for_approval" && current.tag !== "editing_plan") return;

    const approvingState = experimentPlannerReducer(current, { type: "APPROVE_SENT" });
    dispatch({ type: "APPROVE_SENT" });
    if (approvingState.tag !== "approving") return;

    setIsApproving(true);
    try {
      const request = buildApprovalRequest({
        experimentPlanId: approvingState.payload.experiment_plan.id,
        draftExperiments: approvingState.draftExperiments,
        selectedExperimentIds: approvingState.selectedExperimentIds,
      });
      streamRef.current?.send({
        command_id: commandId("cmd_approve"),
        type: "approval.approve",
        agent_run_id: approvingState.agentRunId,
        approval_id: approvingState.approvalId,
        final_experiments: request.final_experiments,
        reason: null,
      });
    } catch (error) {
      dispatch({ type: "APPROVE_FAILED", message: error instanceof Error ? error.message : "Approval failed." });
    }
  }

  function rejectApproval(reason = "User rejected the experiment plan.") {
    const current = stateRef.current;
    if (current.tag !== "waiting_for_approval" && current.tag !== "editing_plan") return;

    streamRef.current?.send({
      command_id: commandId("cmd_reject"),
      type: "approval.reject",
      agent_run_id: current.agentRunId,
      approval_id: current.approvalId,
      final_experiments: null,
      reason,
    });
    dispatch({ type: "REJECT_SENT", reason });
  }

  async function cancelRun(reason = "User cancelled the agent run.") {
    const current = stateRef.current;
    if (!("agentRunId" in current) || !current.agentRunId) return;

    streamRef.current?.send({
      command_id: commandId("cmd_cancel"),
      type: "run.cancel",
      agent_run_id: current.agentRunId,
      approval_id: "approvalId" in current ? current.approvalId : null,
      final_experiments: null,
      reason,
    });

    if (!streamRef.current) {
      await api.cancelAgentRun(current.agentRunId, reason);
    }
    dispatch({ type: "CANCEL_SENT", reason });
  }

  function editExperiment(experimentId: string, title: string) {
    const current = stateRef.current;
    if (current.tag !== "waiting_for_approval" && current.tag !== "editing_plan") return;

    const draftExperiments = current.draftExperiments.map((experiment) => (experiment.id === experimentId ? { ...experiment, title } : experiment));
    streamRef.current?.send({
      command_id: commandId("cmd_update_payload"),
      type: "approval.update_payload",
      agent_run_id: current.agentRunId,
      approval_id: current.approvalId,
      final_experiments: draftExperiments.filter((experiment) => current.selectedExperimentIds.includes(experiment.id)),
      reason: null,
    });
    dispatch({ type: "EDIT_EXPERIMENT", experimentId, patch: { title } });
  }

  useEffect(() => {
    if (state.tag !== "approving") {
      setIsApproving(false);
    }
  }, [state.tag]);

  const primaryHypothesis = currentHypotheses[0] ?? lastHypothesesRef.current[0] ?? null;
  const primaryExperiment = draftExperiments(state)[0] ?? finalExperiments(state)[0] ?? null;
  const signalGate: GateReview | null = lastSignalRef.current
    ? {
        id: "signal",
        title: "Signal Review",
        status: state.tag === "signal_review" ? "active" : "complete",
        signal: lastSignalRef.current,
        actionLabel: state.tag === "signal_review" ? "Use this signal" : "Signal accepted",
      }
    : null;
  const approvalGate: GateReview | null =
    state.tag === "waiting_for_approval" || state.tag === "editing_plan" || state.tag === "approving" || state.tag === "approved"
      ? {
          id: "approval",
          title: "Experiment Approval",
          status: state.tag === "approved" ? "complete" : "active",
          hypothesis: primaryHypothesis,
          experiment: primaryExperiment,
          actionLabel: state.tag === "approved" ? "Approved" : "Approve Experiments",
        }
      : null;
  const gates = [signalGate, approvalGate].filter((gate): gate is GateReview => gate !== null);
  const currentGate = gates.find((gate) => gate.status === "active") ?? null;
  const gateHistory = gates.filter((gate) => gate !== currentGate);
  const displayState = agentState(state);
  const currentFileOrLast = currentFile ?? lastFileRef.current;
  const currentImportOrLast = currentImportResult ?? lastImportRef.current;
  const currentMessages = [...messages(state), ...localUserMessages];
  const currentDocuments = documents(state);
  const currentObservations = observations(state);
  const currentDraftExperiments = draftExperiments(state);
  const currentFinalExperiments = finalExperiments(state);
  const currentApproval = approval(state);
  const currentCalendarEvents = calendarEvents(state);
  const liveThreadActivity = currentMessages.length > 0 || currentDocuments.length > 0 || currentObservations.length > 0;
  const statusRows = buildStatusRows(state, currentImportOrLast, liveThreadActivity);
  const screen: PlannerScreenView = {
    mode: screenMode(state, displayState),
    intro:
      liveThreadActivity || statusRows.length > 0 || primaryExperiment || currentApproval || stateMessage(state)
        ? null
        : {
            title: "Find the signal in this campaign.",
            description: "Attach campaign metrics and add context to start the analysis run.",
          },
    statusRows,
    errorMessage: stateMessage(state),
  };
  const composer = composerFromState(state, displayState, currentQuestion, currentFileOrLast?.name ?? null);
  const progress: PlannerProgressView = {
    visible: displayState !== "idle" && displayState !== "selected",
    runLabel: runShortId(state),
    stateLabel: readableWorkflowState(state, displayState),
    steps: buildChecklist(state),
  };
  const shell: PlannerShellView = {
    campaignName: "Comeback Teaser",
    campaignStatus: displayState === "approved" ? "approved" : displayState === "ready" ? "needs_review" : displayState === "error" ? "error" : "active",
  };
  const streamMessages = streamMessagesFromState({
    messages: currentMessages,
    timelineItems: timelineItems(state),
    primaryExperiment,
    approval: currentApproval,
    calendarEvents: currentCalendarEvents,
    errorMessage: stateMessage(state),
    stateLabel: progress.stateLabel,
  });
  const thread: PlannerThreadView = {
    hasActivity: statusRows.length > 0 || liveThreadActivity || toolLogs(state).length > 0 || Boolean(primaryExperiment) || Boolean(currentApproval) || Boolean(stateMessage(state)),
    streamMessages,
    userMessages: currentMessages.filter((message) => message.role === "user"),
    assistantMessages: currentMessages.filter((message) => message.role === "assistant"),
    documents: currentDocuments,
    observations: currentObservations,
    toolLogs: toolLogs(state),
    timelineItems: timelineItems(state),
    primaryExperiment,
  };
  const inspector: PlannerInspectorView = {
    canToggle: Boolean(currentGate) || gateHistory.length > 0 || Boolean(currentApproval),
    activeGateKey: currentGate ? `${currentGate.id}:${currentGate.status}` : null,
    currentGate,
    history: gateHistory,
  };
  const approvalView: PlannerApprovalView = {
    canApprove: displayState === "ready" && currentDraftExperiments.length > 0 && !isApproving,
    isApproving,
    draftExperiments: currentDraftExperiments,
    finalExperiments: currentFinalExperiments,
    primaryExperiment,
    receipt: currentApproval,
    calendarEvents: currentCalendarEvents,
  };

  return {
    shell,
    screen,
    composer,
    progress,
    thread,
    inspector,
    approval: approvalView,
    importResult: currentImportOrLast,
    signals: currentSignals.length > 0 ? currentSignals : lastSignalsRef.current,
    hypotheses: currentHypotheses.length > 0 ? currentHypotheses : lastHypothesesRef.current,
    toolLogs: toolLogs(state),
    streamRecoveryStatus: streamRecoveryStatus(state),
    commands: {
      updateQuestion: (question) => {
        composerQuestionRef.current = question;
        setComposerQuestion(question);
        dispatch({ type: "UPDATE_QUESTION", question });
      },
      selectCsv: (file) => dispatch({ type: "SELECT_CSV", file }),
      sendMessage: sendComposerMessage,
      analyze,
      continueSignalReview,
      editExperiment,
      approve: approvePlan,
      reject: rejectApproval,
      cancel: cancelRun,
      reset: () => {
        lastFileRef.current = null;
        lastImportRef.current = null;
        lastSignalRef.current = null;
        lastSignalsRef.current = [];
        lastHypothesesRef.current = [];
        composerQuestionRef.current = stateQuestion(initialExperimentPlannerState);
        setComposerQuestion(stateQuestion(initialExperimentPlannerState));
        setLocalUserMessages([]);
        dispatch({ type: "RESET" });
      },
    },
  };
}
