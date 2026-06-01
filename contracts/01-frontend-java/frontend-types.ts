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
  | "FAILED";

export type ToolCallStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";

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
  next_poll_url: string;
  created_at: string;
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
