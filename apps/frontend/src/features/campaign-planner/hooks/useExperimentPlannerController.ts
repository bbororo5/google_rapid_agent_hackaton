"use client";

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { AgentStreamConnection, AgentStreamApi } from "../api/agentStreamApi";
import { createFetchExperimentPlannerApi, type ExperimentPlannerApi } from "../api/experimentPlannerApi";
import { createMockAgentStreamApi } from "../api/mockAgentStreamApi";
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

export type GateReview =
  | {
      id: "import";
      title: "Import Review";
      status: "active" | "complete";
      importResult: ImportCsvResponse;
      fileName: string;
      actionLabel: string;
    }
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

export interface ExperimentPlannerViewModel {
  state: ExperimentPlannerState;
  agentState: "idle" | "selected" | "importing" | "processing" | "ready" | "approved" | "error";
  currentFile: File | null;
  question: string;
  signals: Signal[];
  hypotheses: Hypothesis[];
  draftExperiments: ExperimentItem[];
  finalExperiments: ExperimentItem[];
  messages: AgentMessage[];
  documents: AgentDocument[];
  observations: AgentObservation[];
  toolLogs: ToolCallLog[];
  approval: ApproveExperimentPlanResponse | null;
  calendarEvents: CalendarEventRef[];
  streamRecoveryStatus: AgentStreamRecoveryStatus;
  reasoningChecklist: ChecklistStep[];
  currentGate: GateReview | null;
  gateHistory: GateReview[];
  isApproving: boolean;
  errorMessage: string | null;
  commands: {
    selectCsv: (file: File) => void;
    updateQuestion: (question: string) => void;
    analyze: () => Promise<void>;
    continueImportReview: () => Promise<void>;
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

function stateSignal(state: ExperimentPlannerState) {
  if (state.tag === "signal_review") return state.signal;
  return payloadSignals(state)[0] ?? null;
}

function buildChecklist(state: ExperimentPlannerState): ChecklistStep[] {
  const complete = "complete" as const;
  const active = "active" as const;
  const pending = "pending" as const;

  if ("steps" in state && state.steps.length > 0) {
    return state.steps.map((step) => ({
      label: stageLabel(step.stage),
      status: step.status === "SUCCEEDED" ? complete : step.status === "IN_PROGRESS" ? active : pending,
    }));
  }

  if (state.tag === "idle" || state.tag === "csv_selected") {
    return [
      { label: "Import metrics", status: pending },
      { label: "Analyze signal", status: pending },
      { label: "Generate hypotheses", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "importing_csv" || state.tag === "import_review") {
    return [
      { label: "Import metrics", status: state.tag === "importing_csv" ? active : complete },
      { label: "Analyze signal", status: pending },
      { label: "Generate hypotheses", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "starting_analysis" || state.tag === "analysis_pending" || state.tag === "stream_connecting") {
    return [
      { label: "Import metrics", status: complete },
      { label: "Analyze signal", status: active },
      { label: "Generate hypotheses", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "analysis_running") {
    return [
      { label: "Import metrics", status: complete },
      { label: "Analyze signal", status: active },
      { label: "Generate hypotheses", status: pending },
      { label: "Review experiment plan", status: pending },
    ];
  }

  if (state.tag === "waiting_for_approval" || state.tag === "editing_plan" || state.tag === "approving" || state.tag === "approved") {
    return [
      { label: "Import metrics", status: complete },
      { label: "Analyze signal", status: complete },
      { label: "Generate hypotheses", status: complete },
      { label: "Review experiment plan", status: state.tag === "approved" ? complete : active },
    ];
  }

  return [
    { label: "Import metrics", status: pending },
    { label: "Analyze signal", status: pending },
    { label: "Generate hypotheses", status: pending },
    { label: "Review experiment plan", status: pending },
  ];
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

function agentState(state: ExperimentPlannerState): ExperimentPlannerViewModel["agentState"] {
  if (state.tag === "csv_selected") return "selected";
  if (state.tag === "importing_csv") return "importing";
  if (state.tag === "import_review" || state.tag === "signal_review") return "ready";
  if (state.tag === "starting_analysis" || state.tag === "analysis_pending" || state.tag === "stream_connecting" || state.tag === "analysis_running") return "processing";
  if (state.tag === "waiting_for_approval" || state.tag === "editing_plan" || state.tag === "approving") return "ready";
  if (state.tag === "approved") return "approved";
  if (state.tag === "analysis_failed" || state.tag === "approval_failed" || state.tag === "import_failed") return "error";
  return "idle";
}

export function useExperimentPlannerController(apiOverride?: ExperimentPlannerApi, streamOverride?: AgentStreamApi): ExperimentPlannerViewModel {
  const [state, dispatch] = useReducer(experimentPlannerReducer, initialExperimentPlannerState);
  const [isApproving, setIsApproving] = useState(false);
  const stateRef = useRef(state);
  const streamRef = useRef<AgentStreamConnection | null>(null);
  const lastFileRef = useRef<File | null>(null);
  const lastImportRef = useRef<ImportCsvResponse | null>(null);
  const lastSignalRef = useRef<Signal | null>(null);
  const lastSignalsRef = useRef<Signal[]>([]);
  const lastHypothesesRef = useRef<Hypothesis[]>([]);
  const api = useMemo(() => apiOverride ?? createFetchExperimentPlannerApi(), [apiOverride]);
  const streamApi = useMemo(() => streamOverride ?? createMockAgentStreamApi(), [streamOverride]);
  stateRef.current = state;

  useEffect(() => {
    return () => {
      streamRef.current?.close();
    };
  }, []);

  const currentFile = stateFile(state);
  const currentQuestion = stateQuestion(state);
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

    try {
      dispatch({ type: "IMPORT_REQUESTED" });
      const importResult = await api.importCsv({
        file: current.file,
        workspaceId: "demo_workspace",
        campaignId: "camp_comeback_teaser",
      });
      dispatch({ type: "IMPORT_SUCCEEDED", importResult });
    } catch (error) {
      dispatch({ type: "IMPORT_FAILED", message: error instanceof Error ? error.message : "Import failed." });
    }
  }

  async function continueImportReview() {
    const current = stateRef.current;
    if (current.tag !== "import_review") return;

    try {
      const startingState = experimentPlannerReducer(current, { type: "IMPORT_CONFIRMED" });
      dispatch({ type: "IMPORT_CONFIRMED" });
      if (startingState.tag !== "starting_analysis") return;

      const accepted = await api.runAgent(buildAgentRunRequest(startingState));
      dispatch({
        type: "RUN_AGENT_ACCEPTED",
        agentRunId: accepted.agent_run_id,
        streamUrl: accepted.stream_url,
        snapshotUrl: accepted.next_poll_url,
      });
      await connectStream(accepted.agent_run_id, accepted.stream_url);
    } catch (error) {
      dispatch({ type: "RUN_AGENT_FAILED", message: error instanceof Error ? error.message : "Analysis failed." });
    }
  }

  function continueSignalReview() {
    const current = stateRef.current;
    if (current.tag !== "signal_review") return;
    dispatch({ type: "SIGNAL_CONFIRMED" });
    streamRef.current?.resume?.();
  }

  async function approvePlan() {
    const current = stateRef.current;
    if (current.tag !== "waiting_for_approval" && current.tag !== "editing_plan") return;

    const approvingState = experimentPlannerReducer(current, { type: "APPROVE_SENT" });
    dispatch({ type: "APPROVE_SENT" });
    if (approvingState.tag !== "approving") return;

    setIsApproving(true);
    try {
      const request = buildApprovalRequest(approvingState);
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
  const importGate: GateReview | null =
    lastImportRef.current && lastFileRef.current
      ? {
          id: "import",
          title: "Import Review",
          status: state.tag === "import_review" ? "active" : "complete",
          importResult: lastImportRef.current,
          fileName: lastFileRef.current.name,
          actionLabel: state.tag === "import_review" ? "Continue analysis" : "Imported",
        }
      : null;
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
  const gates = [importGate, signalGate, approvalGate].filter((gate): gate is GateReview => gate !== null);
  const currentGate = gates.find((gate) => gate.status === "active") ?? null;
  const gateHistory = gates.filter((gate) => gate !== currentGate);

  return {
    state,
    agentState: agentState(state),
    currentFile: currentFile ?? lastFileRef.current,
    question: currentQuestion,
    signals: currentSignals.length > 0 ? currentSignals : lastSignalsRef.current,
    hypotheses: currentHypotheses.length > 0 ? currentHypotheses : lastHypothesesRef.current,
    draftExperiments: draftExperiments(state),
    finalExperiments: finalExperiments(state),
    messages: messages(state),
    documents: documents(state),
    observations: observations(state),
    toolLogs: toolLogs(state),
    approval: approval(state),
    calendarEvents: calendarEvents(state),
    streamRecoveryStatus: streamRecoveryStatus(state),
    reasoningChecklist: buildChecklist(state),
    currentGate,
    gateHistory,
    // Keep this derived in the controller for now. The thread can later render richer observation cards.
    isApproving,
    errorMessage: stateMessage(state),
    commands: {
      updateQuestion: (question) => dispatch({ type: "UPDATE_QUESTION", question }),
      selectCsv: (file) => dispatch({ type: "SELECT_CSV", file }),
      analyze,
      continueImportReview,
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
        dispatch({ type: "RESET" });
      },
    },
  };
}
