import type {
  AgentResultPayload,
  AgentDocument,
  StreamMessage,
  AgentMessage,
  MessageAttachment,
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
  MessageAttachment,
  ApproveExperimentPlanResponse,
  ApprovalCommitResult,
  CalendarEventRef,
  ExperimentItem,
  ImportCsvResponse,
  Signal,
  Hypothesis,
  ToolCallLog,
};

export type PlannerPhase =
  | "idle"
  | "input_ready"
  | "importing"
  | "import_failed"
  | "starting"
  | "connecting"
  | "live"
  | "signal_review"
  | "awaiting_approval"
  | "approved"
  | "cancelled"
  | "failed"
  | "approval_failed"
  | "restore_selecting"
  | "restoring_context"
  | "restored_context";

export type AgentStreamRecoveryStatus = "idle";

export interface AgentThreadObservation {
  id: string;
  kind: "progress" | "evidence" | "signal" | "hypothesis" | "plan" | "warning";
  title: string;
  summary: string;
  evidence_refs?: string[];
}

export type AgentTimelineItem =
  | { id: string; sequence: number; kind: "user_message"; message: AgentMessage }
  | { id: string; sequence: number; kind: "assistant_message"; message: AgentMessage }
  | { id: string; sequence: number; kind: "document"; document: AgentDocument }
  | { id: string; sequence: number; kind: "artifact"; artifactKind: "signal" | "hypothesis" | "experiment_plan" | "growth_brief" | "generic"; title: string; content: unknown }
  | { id: string; sequence: number; kind: "observation"; observation: AgentThreadObservation }
  | { id: string; sequence: number; kind: "tool"; tool: ToolCallLog };

export interface ComposerState {
  question: string;
  file: File | null;
}

export interface ThreadState {
  threadId: string | null;
  streamUrl: string | null;
  connection: "idle" | "connecting" | "open" | "closed" | "error";
  messages: AgentMessage[];
  documents: AgentDocument[];
  observations: AgentThreadObservation[];
  toolLogs: ToolCallLog[];
  timelineItems: AgentTimelineItem[];
  receivedMessageIds: string[];
  lastReceivedSequence: number;
  recoveryStatus: AgentStreamRecoveryStatus;
}

export interface ReviewState {
  payload: AgentResultPayload | null;
  activeSignalId: string | null;
  confirmedSignalId: string | null;
  approvalId: string | null;
  // Null = show/approve all hypotheses' experiments. Set = filter to one hypothesis.
  selectedHypothesisId: string | null;
  selectedExperimentIds: string[];
  draftExperiments: ExperimentItem[];
  dirty: boolean;
  approving: boolean;
  approval: ApproveExperimentPlanResponse | null;
  approvalResult: ApprovalCommitResult | null;
  approvalSequence: number | null;
  calendarEvents: CalendarEventRef[];
}

export interface RestoreContextState {
  parentBriefId: string | null;
  previousHypothesis: string;
  previousActionSummary: string;
  observedResultSummary: string | null;
  continuityPrompt: string;
}

export interface ExperimentPlannerState {
  phase: PlannerPhase;
  composer: ComposerState;
  importResult: ImportCsvResponse | null;
  thread: ThreadState;
  review: ReviewState;
  restore: RestoreContextState;
  error: { message: string; recoverable: boolean } | null;
}

export type ExperimentPlannerEvent =
  | { type: "UPDATE_QUESTION"; question: string }
  | { type: "SELECT_CSV"; file: File }
  | { type: "CLEAR_SELECTED_CSV" }
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
  | { type: "TOGGLE_EXPERIMENT"; experimentId: string }
  | { type: "SELECT_HYPOTHESIS"; hypothesisId: string }
  | { type: "APPROVE_SENT" }
  | { type: "SESSION_COMPLETED"; approval: ApproveExperimentPlanResponse }
  | { type: "APPROVE_FAILED"; message: string }
  | { type: "CANCEL_SENT"; reason?: string }
  | { type: "REJECT_SENT"; reason?: string }
  | { type: "SESSION_CANCELLED"; message: string }
  | { type: "RESET" };
