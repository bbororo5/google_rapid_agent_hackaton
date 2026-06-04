import type {
  AgentResultPayload,
  AgentDocument,
  StreamMessage,
  AgentMessage,
  ApproveExperimentPlanResponse,
  ApprovalCommitResult,
  CalendarEventRef,
  ExperimentItem,
  ImportCsvResponse,
  Signal,
  Hypothesis,
  ToolCallLog,
} from "@contracts/frontend-types";

export type {
  AgentResultPayload,
  AgentDocument,
  StreamMessage,
  AgentMessage,
  ApproveExperimentPlanResponse,
  ApprovalCommitResult,
  CalendarEventRef,
  ExperimentItem,
  ImportCsvResponse,
  Signal,
  Hypothesis,
  ToolCallLog,
};

export type AgentProcessingStatus =
  | "PENDING"
  | "ANALYZING_SIGNAL"
  | "SEARCHING_EVIDENCE"
  | "GENERATING_HYPOTHESIS"
  | "DRAFTING_EXPERIMENT"
  | "WAITING_FOR_APPROVAL"
  | "SUCCESS"
  | "FAILED"
  | "CANCELLED";

export type AgentActivityStage =
  | "IMPORT_METRICS"
  | "DETECT_PERFORMANCE_SIGNAL"
  | "GROUND_WITH_EVIDENCE"
  | "GENERATE_HYPOTHESIS"
  | "DRAFT_EXPERIMENT_PLAN"
  | "WAIT_FOR_APPROVAL"
  | "APPLY_APPROVED_PLAN";

export type AgentActivityStatus = "PENDING" | "IN_PROGRESS" | "SUCCEEDED" | "FAILED" | "SKIPPED";

export interface AgentActivitySnapshot {
  id: string;
  order: number;
  stage: AgentActivityStage;
  status: AgentActivityStatus;
}

export interface AgentThreadObservation {
  id: string;
  kind: "progress" | "evidence" | "signal" | "hypothesis" | "plan" | "warning";
  title: string;
  summary: string;
  evidence_refs?: string[];
}

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
  | { id: string; sequence: number; kind: "observation"; observation: AgentThreadObservation }
  | { id: string; sequence: number; kind: "tool"; tool: ToolCallLog };

export type ExperimentPlannerState =
  | { tag: "idle"; question: string }
  | { tag: "csv_selected"; file: File; question: string }
  | { tag: "importing_csv"; file: File; question: string }
  | { tag: "import_succeeded"; file: File; importResult: ImportCsvResponse; question: string }
  | { tag: "import_failed"; file?: File; question: string; message: string }
  | { tag: "starting_analysis"; source: StartingAnalysisSource }
  | { tag: "analysis_pending"; threadId: string; streamUrl: string; status: "PENDING"; toolLogs: ToolCallLog[] }
  | {
      tag: "stream_connecting";
      threadId: string;
      streamUrl: string;
      toolLogs: ToolCallLog[];
      lastReceivedSequence: number;
      messages: AgentMessage[];
      documents: AgentDocument[];
      timelineItems: AgentTimelineItem[];
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "analysis_running";
      threadId: string;
      streamUrl: string;
      status: Exclude<AgentProcessingStatus, "PENDING" | "WAITING_FOR_APPROVAL" | "SUCCESS" | "FAILED" | "CANCELLED">;
      currentStage: string | null;
      steps: AgentActivitySnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentThreadObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "signal_review";
      threadId: string;
      streamUrl: string;
      status: Exclude<AgentProcessingStatus, "PENDING" | "WAITING_FOR_APPROVAL" | "SUCCESS" | "FAILED" | "CANCELLED">;
      currentStage: string | null;
      signal: Signal;
      payload: AgentResultPayload;
      steps: AgentActivitySnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentThreadObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "waiting_for_approval";
      threadId: string;
      streamUrl: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentActivitySnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentThreadObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "editing_plan";
      threadId: string;
      streamUrl: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentActivitySnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentThreadObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
      dirty: true;
    }
  | {
      tag: "approving";
      threadId: string;
      streamUrl: string;
      approvalId: string;
      payload: AgentResultPayload;
      selectedExperimentIds: string[];
      draftExperiments: ExperimentItem[];
      steps: AgentActivitySnapshot[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentThreadObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "approved";
      threadId: string;
      approval: ApproveExperimentPlanResponse;
      approvalResult: ApprovalCommitResult | null;
      calendarEvents: CalendarEventRef[];
      finalExperiments: ExperimentItem[];
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentThreadObservation[];
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
      threadId: string;
      message: string;
      messages: AgentMessage[];
      documents: AgentDocument[];
      observations: AgentThreadObservation[];
      toolLogs: ToolCallLog[];
      timelineItems: AgentTimelineItem[];
      lastReceivedSequence: number;
      recoveryStatus: AgentStreamRecoveryStatus;
    }
  | {
      tag: "analysis_failed" | "approval_failed";
      threadId?: string;
      message: string;
      recoverable: boolean;
    };

export type ExperimentPlannerEvent =
  | { type: "UPDATE_QUESTION"; question: string }
  | { type: "SELECT_CSV"; file: File }
  | { type: "IMPORT_REQUESTED" }
  | { type: "IMPORT_SUCCEEDED"; importResult: ImportCsvResponse }
  | { type: "IMPORT_FAILED"; message: string }
  | { type: "AGENT_SESSION_REQUESTED" }
  | { type: "AGENT_SESSION_ACCEPTED"; threadId: string; streamUrl: string }
  | { type: "AGENT_SESSION_FAILED"; message: string }
  | { type: "STREAM_CONNECT_REQUESTED" }
  | { type: "STREAM_CONNECTED" }
  | { type: "STREAM_EVENT_RECEIVED"; message: StreamMessage }
  | { type: "SIGNAL_CONFIRMED" }
  | { type: "STREAM_FAILED"; threadId?: string; message: string }
  | { type: "EDIT_EXPERIMENT"; experimentId: string; patch: Partial<ExperimentItem> }
  | { type: "APPROVE_SENT" }
  | { type: "RUN_COMPLETED"; approval: ApproveExperimentPlanResponse }
  | { type: "APPROVE_FAILED"; message: string }
  | { type: "CANCEL_SENT"; reason?: string }
  | { type: "REJECT_SENT"; reason?: string }
  | { type: "RUN_CANCELLED"; message: string }
  | { type: "RESET" };
