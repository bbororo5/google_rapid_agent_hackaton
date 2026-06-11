export type Channel = "youtube" | "tiktok" | "instagram" | "x" | "unknown";

export type Confidence = "low" | "medium" | "medium_high" | "high";

export type ToolCallStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";

export type AgentStreamClientCommandType = "message.send";

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
  attachments?: MessageAttachment[];
}

export type StreamMessageRole = "user" | "assistant" | "system";

export type MessageBlockKind = "text" | "activity" | "markdown_document" | "artifact" | "approval" | "result" | "error";

export type MessageAttachmentKind = "csv_import" | "growth_brief" | "document" | "artifact";

export interface MessageAttachment {
  kind: MessageAttachmentKind;
  id: string;
  title?: string;
  filename?: string;
}

export type MessageBlock =
  | { kind: "text"; text: string }
  | { kind: "activity"; id?: string; title: string; status: "queued" | "running" | "done" | "failed"; detail?: string }
  | { kind: "markdown_document"; id: string; title: string; summary?: string; markdown: string }
  | { kind: "artifact"; id: string; artifact_kind: "signal" | "hypothesis" | "experiment_plan" | "growth_brief" | "generic"; title: string; content: unknown }
  | { kind: "approval"; id: string; title: string; target_id: string; actions: ("approve" | "reject" | "request_changes")[]; payload?: AgentResultPayload }
  | { kind: "result"; title: string; detail?: string; refs?: Array<{ kind: string; id: string; title: string }>; approval_result?: ApprovalCommitResult }
  | { kind: "error"; title: string; detail?: string; retryable?: boolean };

export interface StreamMessage {
  id: string;
  thread_id: string;
  sequence: number;
  role: StreamMessageRole;
  created_at: string;
  blocks: MessageBlock[];
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

export type AgentStreamServerFrame = StreamMessage;

export interface MessageSendCommand {
  command_id: string;
  type: "message.send";
  thread_id: string;
  content: string;
  attachments?: MessageAttachment[];
  action?: {
    name: "approve" | "reject" | "request_changes" | "open_document" | "revise_artifact" | "cancel";
    target_id?: string | null;
    payload?: unknown;
  };
  client_created_at: string;
}

export type AgentStreamClientCommand = MessageSendCommand;

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
  display_title?: string;
  display_detail?: string | null;
  status: ToolCallStatus;
  duration_ms: number | null;
  error_message?: string | null;
}

export interface ApproveExperimentPlanRequest {
  experiment_plan_id: string;
  approved_by: string;
  final_experiments: ExperimentItem[];
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
