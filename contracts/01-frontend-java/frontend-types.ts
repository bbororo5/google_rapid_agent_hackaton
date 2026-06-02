export type Channel = "youtube" | "tiktok" | "instagram" | "x" | "unknown";

export type Confidence = "low" | "medium" | "medium_high" | "high";

export type AgentRunStatus =
  | "PENDING"
  | "RUNNING_SIGNAL_DETECTION"
  | "RUNNING_EVIDENCE_SEARCH"
  | "RUNNING_HYPOTHESIS_GENERATION"
  | "RUNNING_EXPERIMENT_GENERATION"
  | "WAITING_FOR_APPROVAL"
  | "SUCCESS"
  | "FAILED"
  | "CANCELLED";

export type ToolCallStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";

export type AgentRunStage =
  | "IMPORT_METRICS"
  | "DETECT_PERFORMANCE_SIGNAL"
  | "GROUND_WITH_EVIDENCE"
  | "GENERATE_HYPOTHESIS"
  | "DRAFT_EXPERIMENT_PLAN"
  | "WAIT_FOR_APPROVAL"
  | "APPLY_APPROVED_PLAN";

export type AgentStepStatus = "PENDING" | "IN_PROGRESS" | "SUCCEEDED" | "FAILED" | "SKIPPED";

export type AgentObservationKind = "progress" | "evidence" | "signal" | "hypothesis" | "plan" | "warning";

export type ApprovalGateKind = "EXPERIMENT_PLAN" | "CREATE_GROWTH_BRIEF" | "CREATE_CALENDAR_EVENTS";

export type AgentStreamServerEventType =
  | "connection.resume_accepted"
  | "connection.replay_started"
  | "connection.replay_completed"
  | "connection.full_sync_required"
  | "connection.reauth_required"
  | "connection.session_expired"
  | "run.started"
  | "step.updated"
  | "user.message.created"
  | "assistant.message.created"
  | "document.created"
  | "observation.created"
  | "tool.updated"
  | "signal.detected"
  | "hypothesis.created"
  | "experiment_plan.drafted"
  | "approval.requested"
  | "approval.committed"
  | "run.paused"
  | "run.resumed"
  | "run.cancelled"
  | "run.completed"
  | "run.failed";

export type AgentStreamClientCommandType =
  | "connection.resume"
  | "connection.full_sync"
  | "run.cancel"
  | "approval.update_payload"
  | "approval.approve"
  | "approval.reject";

export type ReplayScope = "missed_events" | "full_timeline";

export interface DateRange {
  start: string;
  end: string;
}

export interface ImportCsvResponse {
  ok: true;
  import_id: string;
  workspace_id: string;
  campaign_id: string;
  indexed_count: number;
  failed_count: number;
  columns: string[];
  created_at: string;
}

export interface AgentRunRequest {
  workspace_id: string;
  campaign_id: string;
  question: string;
  date_range: DateRange;
  parent_brief_id?: string | null;
}

export interface AgentRunAcceptedResponse {
  ok: true;
  agent_run_id: string;
  status: "PENDING";
  stream_url: string;
  next_poll_url: string;
  created_at: string;
}

export interface AgentStepSnapshot {
  id: string;
  order: number;
  stage: AgentRunStage;
  status: AgentStepStatus;
}

export interface AgentObservation {
  id: string;
  kind: AgentObservationKind;
  title: string;
  summary: string;
  evidence_refs?: string[];
}

export interface ApprovalGateRequest {
  approval_id: string;
  gate: ApprovalGateKind;
  payload: AgentResultPayload;
}

export interface ApprovalCommitResult {
  approval_id: string;
  growth_brief_id: string;
  created_calendar_events: CalendarEventRef[];
  persisted_at: string;
}

export interface AgentMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
}

export type AgentDocumentKind = "evidence_scan" | "signal_summary" | "hypothesis_brief" | "experiment_plan" | "approval_receipt" | "generic";

export interface AgentDocument {
  document_id: string;
  kind: AgentDocumentKind;
  title: string;
  format: "markdown";
  summary: string;
  content: string;
}

export interface AgentStreamServerEvent {
  event_id: string;
  type: AgentStreamServerEventType;
  agent_run_id?: string | null;
  session_id?: string | null;
  sequence?: number | null;
  occurred_at: string;
  status?: AgentRunStatus | null;
  replay_scope?: ReplayScope | null;
  last_replayed_sequence?: number | null;
  next_expected_sequence?: number | null;
  step?: AgentStepSnapshot | null;
  message?: AgentMessage | null;
  document?: AgentDocument | null;
  observation?: AgentObservation | null;
  tool_call?: ToolCallLog | null;
  payload?: AgentResultPayload | null;
  approval_result?: ApprovalCommitResult | null;
  approval?: ApprovalGateRequest | null;
  error_message?: string | null;
}

export interface ConnectionResumeCommand {
  command_id: string;
  type: "connection.resume";
  client_id: string;
  session_id?: string | null;
  agent_run_id: string;
  last_received_sequence: number;
}

export interface ConnectionFullSyncCommand {
  command_id: string;
  type: "connection.full_sync";
  client_id: string;
  session_id?: string | null;
  agent_run_id: string;
}

export interface RuntimeCommand {
  command_id: string;
  type: "run.cancel" | "approval.update_payload" | "approval.approve" | "approval.reject";
  agent_run_id: string;
  approval_id?: string | null;
  final_experiments?: ExperimentItem[] | null;
  reason?: string | null;
}

export type AgentStreamClientCommand =
  | ConnectionResumeCommand
  | ConnectionFullSyncCommand
  | RuntimeCommand;

export interface AgentStreamAck {
  ok: true;
  command_id: string;
  agent_run_id: string;
  accepted_at: string;
}

export interface AgentRunStatusResponse {
  agent_run_id: string;
  status: AgentRunStatus;
  current_stage: string | null;
  retry_count: number;
  error_message: string | null;
  payload: AgentResultPayload | null;
  tool_call_logs: ToolCallLog[];
}

export interface AgentResultPayload {
  signals: Signal[];
  hypotheses: Hypothesis[];
  experiment_plan: ExperimentPlan;
}

export interface Signal {
  id: string;
  type: string;
  title: string;
  description: string;
  metric_name: string;
  current_value: number;
  baseline_value: number;
  lift_ratio: number;
  date_window: DateRange;
  confidence: Confidence;
  evidence_refs: string[];
}

export interface Hypothesis {
  id: string;
  signal_ids: string[];
  statement: string;
  rationale: string;
  confidence: Confidence;
  supporting_evidence_refs: string[];
  caveats: string[];
}

export interface ExperimentPlan {
  id: string;
  summary: string;
  overall_confidence: Confidence;
  items: ExperimentItem[];
}

export interface ExperimentItem {
  id: string;
  hypothesis_id: string;
  title: string;
  channel: Channel;
  content_format: string;
  hook: string;
  cta: string;
  target_metric: string;
  success_criteria: string;
  scheduled_at: string;
  production_brief: string;
}

export interface ToolCallLog {
  sequence: number;
  tool_name: string;
  status: ToolCallStatus;
  duration_ms: number | null;
  error_message?: string | null;
}

export interface ApproveExperimentPlanRequest {
  experiment_plan_id: string;
  approved_by: string;
  final_experiments: ExperimentItem[];
}

export interface CancelAgentRunRequest {
  reason?: string;
}

export interface CancelAgentRunResponse {
  ok: true;
  agent_run_id: string;
  status: "CANCELLED";
  cancelled_at: string;
}

export interface CalendarEventRef {
  event_id: string;
  title: string;
  scheduled_at: string;
}

export interface ApproveExperimentPlanResponse {
  ok: true;
  message: string;
  growth_brief_id: string;
  created_calendar_events: CalendarEventRef[];
  persisted_at: string;
}

export interface ErrorResponse {
  ok: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id: string;
  };
}
