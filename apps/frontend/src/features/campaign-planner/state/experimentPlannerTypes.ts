import type {
  AgentResultPayload,
  AgentRunStatus,
  AgentStepSnapshot,
  AgentDocument,
  AgentObservation,
  StreamMessage,
  AgentRunStage,
  AgentMessage,
  ApproveExperimentPlanResponse,
  ApprovalCommitResult,
  ApprovalGateRequest,
  CalendarEventRef,
  ExperimentItem,
  ImportCsvResponse,
  Signal,
  Hypothesis,
  ToolCallLog,
} from "@contracts/frontend-types";

export type {
  AgentResultPayload,
  AgentRunStatus,
  AgentStepSnapshot,
  AgentDocument,
  AgentObservation,
  StreamMessage,
  AgentRunStage,
  AgentMessage,
  ApproveExperimentPlanResponse,
  ApprovalCommitResult,
  ApprovalGateRequest,
  CalendarEventRef,
  ExperimentItem,
  ImportCsvResponse,
  Signal,
  Hypothesis,
  ToolCallLog,
};

export type StartingAnalysisSource =
  | { kind: "csv_import"; importResult: ImportCsvResponse; question: string }
  | {
      kind: "continued_brief";
      parentBriefId: string;
      previousHypothesis: string;
      previousActionSummary: string;
      observedResultSummary: string | null;
      continuityPrompt: string;
    };

export type AgentStreamRecoveryStatus = "idle";

export type AgentTimelineItem =
  | { id: string; sequence: number; kind: "assistant_message"; message: AgentMessage }
  | { id: string; sequence: number; kind: "document"; document: AgentDocument }
  | { id: string; sequence: number; kind: "observation"; observation: AgentObservation }
  | { id: string; sequence: number; kind: "tool"; tool: ToolCallLog };

export type ExperimentPlannerState =
  | { tag: "idle"; question: string }
  | { tag: "csv_selected"; file: File; question: string }
  | { tag: "importing_csv"; file: File; question: string }
  | { tag: "import_succeeded"; file: File; importResult: ImportCsvResponse; question: string }
  | { tag: "import_failed"; file?: File; question: string; message: string }
  | { tag: "starting_analysis"; source: StartingAnalysisSource }
  | { tag: "analysis_pending"; agentRunId: string; streamUrl: string; snapshotUrl: string; status: "PENDING"; toolLogs: ToolCallLog[] }
  | {
      tag: "stream_connecting";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      toolLogs: ToolCallLog[];
      lastReceivedSequence: number;
      messages: AgentMessage[];
      documents: AgentDocument[];
      timelineItems: AgentTimelineItem[];
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "analysis_running";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      status: Exclude<AgentRunStatus, "PENDING" | "WAITING_FOR_APPROVAL" | "SUCCESS" | "FAILED" | "CANCELLED">;
      currentStage: string | null;
      steps: AgentStepSnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "signal_review";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      status: Exclude<AgentRunStatus, "PENDING" | "WAITING_FOR_APPROVAL" | "SUCCESS" | "FAILED" | "CANCELLED">;
      currentStage: string | null;
      signal: Signal;
      payload: AgentResultPayload;
      steps: AgentStepSnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "waiting_for_approval";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentStepSnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "editing_plan";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentStepSnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
      dirty: true;
    }
  | {
      tag: "approving";
      agentRunId: string;
      streamUrl: string;
      snapshotUrl: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentStepSnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "approved";
      agentRunId: string;
      approval: ApproveExperimentPlanResponse;
      approvalResult: ApprovalCommitResult | null;
      calendarEvents: CalendarEventRef[];
      finalExperiments: ExperimentItem[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | { tag: "restore_selecting"; parentBriefId: string }
  | { tag: "restoring_context"; parentBriefId: string }
  | {
      tag: "restored_context";
      parentBriefId: string;
      previousHypothesis: string;
      previousActionSummary: string;
      observedResultSummary: string | null;
      continuityPrompt: string;
    }
  | {
      tag: "analysis_cancelled";
      agentRunId: string;
      message: string;
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "analysis_failed" | "approval_failed";
      agentRunId?: string;
      message: string;
      recoverable: boolean;
    };

export type ExperimentPlannerEvent =
  | { type: "UPDATE_QUESTION"; question: string }
  | { type: "SELECT_CSV"; file: File }
  | { type: "IMPORT_REQUESTED" }
  | { type: "IMPORT_SUCCEEDED"; importResult: ImportCsvResponse }
  | { type: "IMPORT_FAILED"; message: string }
  | { type: "RUN_AGENT_REQUESTED" }
  | { type: "RUN_AGENT_ACCEPTED"; agentRunId: string; streamUrl: string; snapshotUrl: string }
  | { type: "RUN_AGENT_FAILED"; message: string }
  | { type: "STREAM_CONNECT_REQUESTED" }
  | { type: "STREAM_CONNECTED" }
  | { type: "STREAM_EVENT_RECEIVED"; message: StreamMessage }
  | { type: "SIGNAL_CONFIRMED" }
  | { type: "STREAM_FAILED"; agentRunId?: string; message: string }
  | { type: "APPROVAL_REQUESTED"; approval: ApprovalGateRequest; toolLogs: ToolCallLog[] }
  | { type: "EDIT_EXPERIMENT"; experimentId: string; patch: Partial<ExperimentItem> }
  | { type: "APPROVE_SENT" }
  | { type: "RUN_COMPLETED"; approval: ApproveExperimentPlanResponse }
  | { type: "APPROVE_FAILED"; message: string }
  | { type: "CANCEL_SENT"; reason?: string }
  | { type: "REJECT_SENT"; reason?: string }
  | { type: "RUN_CANCELLED"; message: string }
  | { type: "RESET" };
