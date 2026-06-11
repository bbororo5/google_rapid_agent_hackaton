"use client";

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { createWebSocketAgentStreamApi, type AgentStreamConnection, type AgentStreamApi } from "../api/agentStreamApi";
import { createFetchExperimentPlannerApi, type ExperimentPlannerApi } from "../api/experimentPlannerApi";
import { buildApprovalRequest } from "../state/experimentPlannerRequests";
import { getCampaign, setCampaignThread } from "../state/campaignStore";
import { initialExperimentPlannerState, experimentPlannerReducer } from "../state/experimentPlannerReducer";
import type {
  ApproveExperimentPlanResponse,
  CalendarEventRef,
  ExperimentItem,
  AgentDocument,
  AgentThreadObservation,
  AgentMessage,
  MessageAttachment,
  AgentStreamRecoveryStatus,
  AgentTimelineItem,
  Hypothesis,
  Signal,
  ToolCallLog,
  ExperimentPlannerState,
  ImportCsvResponse,
  PlannerPhase,
} from "../state/experimentPlannerTypes";

export interface ChecklistStep {
  label: string;
  status: "complete" | "active" | "pending";
}

type AgentDisplayState = "idle" | "selected" | "importing" | "processing" | "ready" | "approved" | "error";

type ThreadLocalUserMessage = AgentMessage & { clientSequence: number; phaseAtSend: PlannerPhase };

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
      hypotheses: Hypothesis[];
      selectedHypothesisId: string | null;
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
  | "starting_session"
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

export type ComposerMode = "prepare_session" | "session_in_progress" | "review_gate" | "approval_gate" | "completed" | "error";

export type ComposerPrimaryAction =
  | { kind: "analyze"; label: "Send"; disabled: boolean; title?: string }
  | { kind: "send"; label: "Send"; disabled: boolean; title?: string }
  | { kind: "stop"; label: "Stop"; disabled: boolean; title?: string }
  | { kind: "retry"; label: "Retry"; disabled: boolean; title?: string }
  | { kind: "new_session"; label: "New session"; disabled: boolean; title?: string }
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
  threadLabel: string | null;
  stateLabel: string;
  steps: ChecklistStep[];
}

export type StreamMessageBlock =
  | { kind: "text"; text: string }
  | { kind: "attachment"; fileName: string; label?: string }
  | { kind: "activity"; id: string; title: string; status: "queued" | "running" | "done" | "failed"; detail?: string }
  | { kind: "markdown_document"; id: string; title: string; summary?: string; markdown: string; document: AgentDocument }
  | { kind: "artifact"; id: string; artifactKind: "signal" | "hypothesis" | "experiment_plan" | "growth_brief" | "generic"; title: string; content: unknown }
  | { kind: "approval"; id: string; title: string; targetId: string; actions: ("approve" | "reject" | "request_changes")[] }
  | { kind: "result"; title: string; detail?: string }
  | { kind: "error"; title: string; detail?: string; retryable?: boolean };

export interface StreamMessage {
  id: string;
  sequence: number;
  role: "user" | "assistant" | "system";
  createdAt: string | null;
  clientPhase?: PlannerPhase;
  blocks: StreamMessageBlock[];
}

export interface ThreadMessageGroup {
  id: string;
  role: "user" | "assistant" | "system";
  sequence: number;
  messages: StreamMessage[];
  blocks: StreamMessageBlock[];
}

export type ThreadDisplayItem =
  | { kind: "message_group"; id: string; sequence: number; group: ThreadMessageGroup }
  | { kind: "decision_gate"; id: string; sequence: number; gate: GateReview };

export interface PlannerThreadView {
  hasActivity: boolean;
  streamMessages: StreamMessage[];
  groups: ThreadMessageGroup[];
  items: ThreadDisplayItem[];
  userMessages: AgentMessage[];
  assistantMessages: AgentMessage[];
  documents: AgentDocument[];
  observations: AgentThreadObservation[];
  toolLogs: ToolCallLog[];
  timelineItems: AgentTimelineItem[];
  primaryExperiment: ExperimentItem | null;
}

export interface PlannerInspectorView {
  canToggle: boolean;
  activeGateKey: string | null;
  currentGate: GateReview | null;
  history: GateReview[];
  outputs: OutputPanelItem[];
}

export interface OutputPanelItem {
  id: string;
  title: string;
  eyebrow: string;
  kind: "document" | "signal" | "experiment_plan" | "approval";
  summary: string;
  markdown: string;
  sequence: number;
}

export interface PlannerApprovalView {
  canApprove: boolean;
  isApproving: boolean;
  selectedExperimentIds: string[];
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
    sendMessage: () => Promise<void>;
    analyze: () => Promise<void>;
    continueSignalReview: () => void;
    editExperiment: (experimentId: string, title: string) => void;
    toggleExperiment: (experimentId: string) => void;
    selectHypothesis: (hypothesisId: string) => void;
    approve: () => Promise<void>;
    reject: (reason?: string) => void;
    cancel: (reason?: string) => Promise<void>;
    reset: () => void;
  };
}

function stateMessage(state: ExperimentPlannerState) {
  return state.error?.message ?? null;
}

function stateFile(state: ExperimentPlannerState) {
  return state.composer.file;
}

function stateQuestion(state: ExperimentPlannerState) {
  return state.composer.question;
}

function payloadSignals(state: ExperimentPlannerState) {
  return state.review.payload?.signals ?? [];
}

function payloadHypotheses(state: ExperimentPlannerState) {
  return state.review.payload?.hypotheses ?? [];
}

function draftExperiments(state: ExperimentPlannerState) {
  return state.review.draftExperiments;
}

function finalExperiments(state: ExperimentPlannerState) {
  if (state.review.approval && state.review.draftExperiments.length > 0) {
    return state.review.draftExperiments.filter((experiment) => state.review.selectedExperimentIds.includes(experiment.id));
  }
  return [];
}

function messages(state: ExperimentPlannerState) {
  return state.thread.messages;
}

function documents(state: ExperimentPlannerState) {
  return state.thread.documents;
}

function toolLogs(state: ExperimentPlannerState) {
  return state.thread.toolLogs;
}

function hasCompletedAnalysisRound(state: ExperimentPlannerState) {
  if (state.review.payload?.signals.length || state.phase === "signal_review") return true;
  return state.thread.timelineItems.some((item) => {
    if (item.kind === "tool") {
      const title = item.tool.display_title ?? item.tool.tool_name;
      return (
        item.tool.status === "SUCCESS" &&
        (/Finished DATA_ANALYSIS round/i.test(title) || /Saved analysis artifacts/i.test(title) || /Saved thread state/i.test(title))
      );
    }
    if (item.kind === "assistant_message") {
      return item.message.content.includes("분석 결과를 확인했습니다");
    }
    return false;
  });
}

function observations(state: ExperimentPlannerState) {
  return state.thread.observations;
}

function timelineItems(state: ExperimentPlannerState) {
  return state.thread.timelineItems;
}

function approval(state: ExperimentPlannerState) {
  return state.review.approval;
}

function calendarEvents(state: ExperimentPlannerState) {
  return state.review.calendarEvents;
}

function streamRecoveryStatus(state: ExperimentPlannerState): AgentStreamRecoveryStatus {
  return state.thread.recoveryStatus;
}

function stateImportResult(state: ExperimentPlannerState) {
  return state.importResult;
}

function commandId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "_")}`;
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function confidenceLabel(value: string) {
  return value.replace("_", " ");
}

function agentThreadStreamUrl(threadId: string) {
  const agentApiBaseUrl = process.env.NEXT_PUBLIC_AGENT_API_BASE_URL ?? "http://localhost:8080";
  return `${agentApiBaseUrl}/api/agent/threads/${threadId}/stream`;
}

function csvPrompt(text: string) {
  const trimmed = text.trim();
  return trimmed || "분석을 도와줘.";
}

function csvAttachment(importResult: ImportCsvResponse, fileName: string): MessageAttachment {
  return {
    kind: "csv_import",
    id: importResult.import_id,
    title: fileName,
    filename: fileName,
  };
}

function attachmentBlocks(attachments: MessageAttachment[] | undefined): StreamMessageBlock[] {
  return (attachments ?? []).map((attachment) => ({
    kind: "attachment" as const,
    fileName: attachment.filename ?? attachment.title ?? attachment.id,
    label: attachment.kind === "csv_import" ? "CSV attached" : attachment.title,
  }));
}

const THREAD_STORAGE_KEY = "launchpilot.thread";

function persistThread(threadId: string, streamUrl: string) {
  try {
    window.localStorage.setItem(THREAD_STORAGE_KEY, JSON.stringify({ threadId, streamUrl }));
  } catch {
    // storage unavailable (private mode) -> best effort
  }
  try {
    // Reflect the live thread in the URL so a refresh (or ?new start) restores
    // this exact conversation instead of a blank slate.
    window.history.replaceState(null, "", `${window.location.pathname}?thread=${encodeURIComponent(threadId)}`);
  } catch {
    // history API unavailable -> best effort
  }
}

function readPersistedThread(): { threadId: string; streamUrl: string } | null {
  try {
    const raw = window.localStorage.getItem(THREAD_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { threadId?: unknown; streamUrl?: unknown };
    return typeof parsed.threadId === "string" && typeof parsed.streamUrl === "string"
      ? { threadId: parsed.threadId, streamUrl: parsed.streamUrl }
      : null;
  } catch {
    return null;
  }
}

function clearPersistedThread() {
  try {
    window.localStorage.removeItem(THREAD_STORAGE_KEY);
  } catch {
    // ignore
  }
}

function toolBlock(tool: ToolCallLog): StreamMessageBlock {
  const status = tool.status === "FAILED" ? "failed" : tool.status === "SUCCESS" ? "done" : tool.status === "RUNNING" ? "running" : "queued";
  return {
    kind: "activity",
    id: `tool:${tool.sequence}:${tool.tool_name}`,
    title: tool.display_title ?? toolStatusLabel(tool),
    status,
    detail: tool.display_detail ?? tool.error_message ?? undefined,
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
  messages: Array<AgentMessage | ThreadLocalUserMessage>;
  timelineItems: AgentTimelineItem[];
  primaryExperiment: ExperimentItem | null;
  approval: ApproveExperimentPlanResponse | null;
  approvalSequence: number | null;
  calendarEvents: CalendarEventRef[];
  errorMessage: string | null;
  stateLabel: string;
}): StreamMessage[] {
  const localUserMessages = input.messages.filter((message) => message.role === "user" && message.message_id.startsWith("msg_local_"));
  // Server-echoed user messages now arrive as user_message timeline items, which
  // keep their real stream sequence so they interleave with assistant blocks.
  const serverUserMessages = input.timelineItems.filter((item) => item.kind === "user_message");
  // Drop optimistic local user bubbles once the server has echoed the same text
  // back into the timeline (otherwise every sent message renders twice).
  const echoedUserCounts = new Map<string, number>();
  const localAttachmentQueues = new Map<string, MessageAttachment[][]>();
  for (const message of localUserMessages) {
    if (!message.attachments?.length) continue;
    const key = message.content.trim();
    localAttachmentQueues.set(key, [...(localAttachmentQueues.get(key) ?? []), message.attachments]);
  }
  for (const item of serverUserMessages) {
    const key = item.message.content.trim();
    echoedUserCounts.set(key, (echoedUserCounts.get(key) ?? 0) + 1);
  }
  const pendingLocalUserMessages = localUserMessages.filter((message) => {
    const key = message.content.trim();
    const remaining = echoedUserCounts.get(key) ?? 0;
    if (remaining > 0) {
      echoedUserCounts.set(key, remaining - 1);
      return false;
    }
    return true;
  });
  const streamMessages: StreamMessage[] = [
    ...input.timelineItems.map((item) => {
      if (item.kind === "user_message") {
        const key = item.message.content.trim();
        const localAttachmentQueue = localAttachmentQueues.get(key) ?? [];
        const fallbackAttachments = localAttachmentQueue.shift() ?? [];
        const attachments = item.message.attachments?.length ? item.message.attachments : fallbackAttachments;
        return {
          id: item.id,
          sequence: item.sequence,
          role: "user" as const,
          createdAt: null,
          blocks: [
            { kind: "text" as const, text: item.message.content },
            ...attachmentBlocks(attachments),
          ],
        };
      }
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
      if (item.kind === "artifact") {
        return {
          id: item.id,
          sequence: item.sequence,
          role: "assistant" as const,
          createdAt: null,
          blocks: [
            {
              kind: "artifact" as const,
              id: item.id.replace(/^artifact:/, ""),
              artifactKind: item.artifactKind,
              title: item.title,
              content: item.content,
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
    ...pendingLocalUserMessages.map((message, index) => {
      return {
        id: message.message_id,
        sequence: "clientSequence" in message ? message.clientSequence : 10_000 + index,
        role: "user" as const,
        createdAt: null,
        clientPhase: "phaseAtSend" in message ? message.phaseAtSend : undefined,
        blocks: [
          { kind: "text" as const, text: message.content },
          ...attachmentBlocks(message.attachments),
        ],
      };
    }),
  ];

  if (input.primaryExperiment) {
    streamMessages.push({
      id: `artifact:${input.primaryExperiment.id}`,
      sequence: input.approvalSequence !== null ? input.approvalSequence - 0.1 : 20_000,
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
      sequence: input.approvalSequence ?? 20_100,
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
      blocks: [{ kind: "error", title: `Agent session · ${input.stateLabel}`, detail: input.errorMessage, retryable: true }],
    });
  }

  return streamMessages.sort((a, b) => a.sequence - b.sequence);
}

function shouldStartThreadGroup(previous: ThreadMessageGroup | null, message: StreamMessage) {
  if (!previous) return true;
  if (previous.role !== message.role) return true;
  if (message.role === "user") return true;
  if (message.role === "system") return true;
  return false;
}

function threadGroupsFromMessages(messages: StreamMessage[]): ThreadMessageGroup[] {
  const groups: ThreadMessageGroup[] = [];

  messages.forEach((message) => {
    const previous = groups.at(-1) ?? null;
    if (previous === null || shouldStartThreadGroup(previous, message)) {
      groups.push({
        id: `group:${message.id}`,
        role: message.role,
        sequence: message.sequence,
        messages: [message],
        blocks: message.blocks,
      });
      return;
    }

    previous.messages.push(message);
    previous.blocks.push(...message.blocks);
  });

  return groups;
}

function gateAnchorPhase(gate: GateReview) {
  return gate.id === "signal" ? "signal_review" : "awaiting_approval";
}

function gateSequence(gate: GateReview, groups: ThreadMessageGroup[], fallback: number) {
  if (gate.id === "signal") {
    const signalId = gate.signal?.id;
    const signalGroup = groups.find((group) =>
      group.blocks.some((block) => block.kind === "artifact" && block.artifactKind === "signal" && (!signalId || block.id === signalId)),
    );
    if (signalGroup) return signalGroup.sequence + 0.001;
  }

  if (gate.id === "approval") {
    const approvalGroup = groups.find((group) => group.blocks.some((block) => block.kind === "approval"));
    if (approvalGroup) return approvalGroup.sequence + 0.001;
    const resultGroup = groups.find((group) => group.blocks.some((block) => block.kind === "result"));
    if (resultGroup) return resultGroup.sequence - 0.001;
  }

  return fallback;
}

function threadDisplayItemsFromProjection(input: { groups: ThreadMessageGroup[]; gates: GateReview[]; currentGate: GateReview | null }): ThreadDisplayItem[] {
  const items: ThreadDisplayItem[] = input.groups.map((group) => ({
    kind: "message_group",
    id: group.id,
    sequence: group.sequence,
    group,
  }));

  input.gates.forEach((gate, index) => {
    const anchorPhase = gateAnchorPhase(gate);
    const anchorGroup = input.groups.find((group) => group.role === "user" && group.messages.some((message) => message.clientPhase === anchorPhase));
    const lastSequence = input.groups.at(-1)?.sequence ?? 0;
    const fallbackSequence = anchorGroup ? anchorGroup.sequence - 0.001 : lastSequence + 0.001 + index * 0.001;
    items.push({
      kind: "decision_gate",
      id: `decision:${gate.id}:${gate.status}`,
      sequence: gateSequence(gate, input.groups, fallbackSequence),
      gate,
    });
  });

  return items.sort((a, b) => a.sequence - b.sequence);
}

function documentPanelItem(document: AgentDocument, index: number): OutputPanelItem {
  return {
    id: `document:${document.document_id}`,
    title: document.kind === "evidence_scan" ? "Evidence notes" : document.title,
    eyebrow: "Markdown document",
    kind: "document",
    summary: document.summary,
    markdown: document.content,
    sequence: index + 1,
  };
}

function signalMarkdown(signal: Signal) {
  return [
    `# ${signal.title}`,
    "",
    `**Signal:** ${signal.metric_name} · ${signal.lift_ratio.toFixed(1)}x · ${confidenceLabel(signal.confidence)}`,
    "",
    signal.description,
    "",
    `- Current: ${formatPercent(signal.current_value)}`,
    `- Baseline: ${formatPercent(signal.baseline_value)}`,
    `- Evidence refs: ${signal.evidence_refs.join(", ")}`,
  ].join("\n");
}

function analysisFallbackOutputFromTimeline(items: AgentTimelineItem[]): OutputPanelItem | null {
  const signalTexts: string[] = [];
  let sawAnalysisCompletion = false;

  items.forEach((item) => {
    if (item.kind === "assistant_message") {
      const content = item.message.content.trim();
      if (!content) return;
      if (content.includes("분석 결과를 확인했습니다")) {
        sawAnalysisCompletion = true;
        return;
      }
      if (/showed .*lift compared to its baseline/i.test(content) || /observed .*lift/i.test(content)) {
        signalTexts.push(content);
      }
    }
    if (item.kind === "tool") {
      const title = item.tool.display_title ?? item.tool.tool_name;
      if (item.tool.status === "SUCCESS" && (/Finished DATA_ANALYSIS round/i.test(title) || /Saved analysis artifacts/i.test(title))) {
        sawAnalysisCompletion = true;
      }
    }
  });

  if (!sawAnalysisCompletion && signalTexts.length === 0) return null;

  const lines = ["# Analysis result", ""];
  if (signalTexts.length > 0) {
    lines.push("## Signals", "", ...signalTexts.map((text) => `- ${text}`));
  } else {
    lines.push("Analysis completed. The structured signal artifact was not available in the client stream.");
  }

  return {
    id: "analysis:fallback",
    title: "Analysis result",
    eyebrow: "Analysis output",
    kind: "document",
    summary: signalTexts.length > 0 ? `${signalTexts.length} signal${signalTexts.length === 1 ? "" : "s"} found` : "Analysis completed",
    markdown: lines.join("\n"),
    sequence: 0,
  };
}

function experimentPlanMarkdown(experiments: ExperimentItem[], hypothesis: Hypothesis | null) {
  const lines = ["# Experiment plan", ""];
  if (hypothesis) {
    lines.push("## Hypothesis", "", hypothesis.statement, "", hypothesis.rationale, "");
  }

  experiments.forEach((experiment, index) => {
    lines.push(`## ${index + 1}. ${experiment.title}`, "");
    lines.push(`- Channel: ${experiment.channel}`);
    lines.push(`- Scheduled: ${experiment.scheduled_at}`);
    lines.push(`- Hook: ${experiment.hook}`);
    lines.push(`- CTA: ${experiment.cta}`);
    lines.push(`- Success criteria: ${experiment.success_criteria}`);
    lines.push("", experiment.production_brief, "");
  });

  return lines.join("\n");
}

function approvalMarkdown(input: { approval: ApproveExperimentPlanResponse; experiments: ExperimentItem[]; calendarEvents: CalendarEventRef[] }) {
  const lines = [
    "# Approval complete",
    "",
    `Growth brief ${input.approval.growth_brief_id} was created.`,
    "",
    "## Approved experiments",
    "",
  ];

  input.experiments.forEach((experiment) => {
    lines.push(`- ${experiment.title} (${experiment.channel}, ${experiment.scheduled_at})`);
  });

  lines.push("", "## Calendar events", "");
  input.calendarEvents.forEach((event) => {
    lines.push(`- ${event.title} · ${event.scheduled_at}`);
  });

  return lines.join("\n");
}

function outputPanelItemsFromState(input: {
  documents: AgentDocument[];
  signalGate: GateReview | null;
  analysisFallback: OutputPanelItem | null;
  approvalGate: GateReview | null;
  draftExperiments: ExperimentItem[];
  finalExperiments: ExperimentItem[];
  approval: ApproveExperimentPlanResponse | null;
  calendarEvents: CalendarEventRef[];
}): OutputPanelItem[] {
  const items = input.documents.map(documentPanelItem);
  let sequence = items.length + 1;

  if (input.signalGate?.id === "signal") {
    items.push({
      id: `signal:${input.signalGate.signal.id}`,
      title: input.signalGate.signal.title,
      eyebrow: input.signalGate.status === "complete" ? "Confirmed signal" : "Analysis result",
      kind: "signal",
      summary: `${input.signalGate.signal.metric_name} · ${input.signalGate.signal.lift_ratio.toFixed(1)}x`,
      markdown: signalMarkdown(input.signalGate.signal),
      sequence: sequence++,
    });
  } else if (input.analysisFallback) {
    items.push({
      ...input.analysisFallback,
      sequence: sequence++,
    });
  }

  if (input.approvalGate?.id === "approval" && input.draftExperiments.length > 0) {
    items.push({
      id: `experiment-plan:${input.draftExperiments.map((experiment) => experiment.id).join(":")}`,
      title: "Experiment plan",
      eyebrow: input.approvalGate.status === "complete" ? "Approved draft" : "Draft artifact",
      kind: "experiment_plan",
      summary: `${input.draftExperiments.length} experiment${input.draftExperiments.length === 1 ? "" : "s"} ready`,
      markdown: experimentPlanMarkdown(input.draftExperiments, input.approvalGate.hypothesis),
      sequence: sequence++,
    });
  }

  if (input.approval) {
    items.push({
      id: `approval:${input.approval.growth_brief_id}`,
      title: "Approval complete",
      eyebrow: "Approved output",
      kind: "approval",
      summary: `${input.calendarEvents.length} calendar event${input.calendarEvents.length === 1 ? "" : "s"} ready`,
      markdown: approvalMarkdown({
        approval: input.approval,
        experiments: input.finalExperiments.length > 0 ? input.finalExperiments : input.draftExperiments,
        calendarEvents: input.calendarEvents,
      }),
      sequence: sequence++,
    });
  }

  return items;
}

function stateSignal(state: ExperimentPlannerState) {
  if (state.review.activeSignalId && state.review.payload) {
    return state.review.payload.signals.find((signal) => signal.id === state.review.activeSignalId) ?? state.review.payload.signals[0] ?? null;
  }
  return state.review.payload?.signals[0] ?? null;
}

function buildChecklist(state: ExperimentPlannerState): ChecklistStep[] {
  const complete = "complete" as const;
  const active = "active" as const;
  const pending = "pending" as const;
  const csvRun = Boolean(state.importResult) || state.phase === "importing";
  const started = Boolean(state.thread.threadId) || ["starting", "connecting", "live", "signal_review", "awaiting_approval", "approved"].includes(state.phase);
  const connected = state.thread.connection === "open" || ["live", "signal_review", "awaiting_approval", "approved"].includes(state.phase);
  const hasSignal = hasCompletedAnalysisRound(state);
  const hasPlan = Boolean(state.review.payload?.experiment_plan.items.length);
  const needsApproval = state.phase === "awaiting_approval" || state.review.approving;
  const approved = state.phase === "approved";

  const setupSteps: ChecklistStep[] = [
    ...(csvRun ? [{ label: "Import metrics", status: state.phase === "importing" ? active : complete } satisfies ChecklistStep] : []),
    { label: "Start agent session", status: state.phase === "starting" ? active : started ? complete : pending },
    { label: "Connect stream", status: state.phase === "connecting" ? active : connected ? complete : started ? active : pending },
  ];

  if (approved || needsApproval || hasPlan) {
    return [
      ...setupSteps,
      { label: "Draft experiment plan", status: hasPlan ? complete : connected ? active : pending },
      { label: "Review approval", status: approved ? complete : needsApproval ? active : pending },
    ];
  }

  return [
    ...setupSteps,
    { label: "Analyze signals", status: hasSignal ? complete : connected ? active : pending },
    { label: "Discuss next step", status: hasSignal ? active : pending },
  ];
}

function agentState(state: ExperimentPlannerState): AgentDisplayState {
  if (state.phase === "input_ready") return "selected";
  if (state.phase === "importing") return "importing";
  if (state.phase === "live" && hasCompletedAnalysisRound(state)) return "ready";
  if (state.phase === "signal_review" || state.phase === "awaiting_approval") return "ready";
  if (["starting", "connecting", "live"].includes(state.phase)) return "processing";
  if (state.phase === "approved") return "approved";
  if (state.phase === "failed" || state.phase === "approval_failed" || state.phase === "import_failed") return "error";
  return "idle";
}

function runShortId(state: ExperimentPlannerState) {
  return state.thread.threadId ? state.thread.threadId.slice(-3) : null;
}

function readableWorkflowState(state: ExperimentPlannerState, displayState: AgentDisplayState) {
  switch (state.phase) {
    case "input_ready":
      return state.importResult ? "Ready to start" : "Ready";
    case "starting":
      return "Starting";
    case "connecting":
      return "Connecting stream";
    case "live":
      return hasCompletedAnalysisRound(state) ? "Ready to discuss" : "Agent responding";
    case "signal_review":
    case "awaiting_approval":
      return "Review needed";
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
  if (state.phase === "idle") return "empty";
  if (state.phase === "input_ready") return "input_ready";
  if (state.phase === "importing") return "importing";
  if (state.phase === "starting") return "starting_session";
  if (state.phase === "connecting") return "connecting_stream";
  if (state.phase === "live") return "live_run";
  if (state.phase === "signal_review") return "signal_review";
  if (state.phase === "awaiting_approval") return "plan_review";
  if (state.phase === "approved") return "approved_summary";
  if (displayState === "error") return "error";
  return "live_run";
}

function composerFromState(state: ExperimentPlannerState, displayState: AgentDisplayState, value: string, fileName: string | null): PlannerComposerView {
  const base = {
    value,
    fileName,
    placeholder: "Add context or instructions for the agent...",
  };

  switch (state.phase) {
    case "idle":
      return {
        ...base,
        mode: "prepare_session",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: {
          kind: "send",
          label: "Send",
          disabled: !value.trim(),
          title: "Send a message to the thread, or attach campaign metrics CSV to start analysis",
        },
      };
    case "input_ready":
      return {
        ...base,
        mode: "prepare_session",
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
    case "importing":
    case "starting":
    case "connecting":
      return {
        ...base,
        mode: "session_in_progress",
        inputDisabled: false,
        canAttachCsv: false,
        primaryAction: {
          kind: "stop",
          label: "Stop",
          disabled: !state.thread.threadId,
          title: "Stop this analysis",
        },
      };
    case "live": {
      // Analysis is in progress when the agent is still producing pipeline output
      // and hasn't reached the approval payload yet. Covers both CSV-started runs
      // (importResult) and chat-started runs (artifact documents stream in); plain
      // free chat produces neither, so it keeps the Send button.
      const analysisInProgress =
        !state.review.payload && !hasCompletedAnalysisRound(state) && (Boolean(state.importResult) || state.thread.documents.length > 0);
      return {
        ...base,
        mode: "session_in_progress",
        inputDisabled: false,
        canAttachCsv: !analysisInProgress,
        primaryAction: analysisInProgress
          ? {
              kind: "stop",
              label: "Stop",
              disabled: !state.thread.threadId,
              title: "Stop this analysis",
            }
          : { kind: "send", label: "Send", disabled: !value.trim() && !fileName, title: "Send a message to the thread" },
      };
    }
    case "signal_review":
      return {
        ...base,
        mode: "review_gate",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim() && !fileName, title: "Send a message to the thread" },
      };
    case "awaiting_approval":
      return {
        ...base,
        mode: "approval_gate",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim() && !fileName, title: "Send a message to the thread" },
      };
    case "approved":
      return {
        ...base,
        mode: "completed",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim() && !fileName, title: "Send a message to the thread" },
      };
    case "failed":
    case "cancelled":
    case "approval_failed":
      return {
        ...base,
        mode: "error",
        inputDisabled: false,
        canAttachCsv: true,
        primaryAction: { kind: "send", label: "Send", disabled: !value.trim() && !fileName, title: "Send a message to the thread" },
      };
    default:
      return {
        ...base,
        mode: displayState === "processing" ? "session_in_progress" : "prepare_session",
        inputDisabled: false,
        canAttachCsv: displayState !== "processing",
        primaryAction: displayState === "processing" ? { kind: "stop", label: "Stop", disabled: true } : { kind: "send", label: "Send", disabled: !value.trim() && !fileName },
      };
  }
}

function buildStatusRows(state: ExperimentPlannerState, importResult: ImportCsvResponse | null, hasLiveThreadActivity: boolean): StatusRow[] {
  switch (state.phase) {
    case "importing":
      return [{ title: "Importing campaign metrics...", detail: "Preparing the evidence store before signal detection." }];
    case "input_ready":
      if (!importResult) return [];
      return [{ title: "Campaign metrics are ready.", detail: `${importResult.indexed_count} rows indexed · ${importResult.failed_count} failed` }];
    case "starting":
      return [
        {
          title: "Starting the agent session...",
          detail: importResult ? `${importResult.indexed_count} rows indexed · ${importResult.failed_count} failed` : "Campaign metrics are indexed.",
        },
      ];
    case "connecting":
      return [{ title: "Connecting live agent stream...", detail: "Signal and evidence events will appear here as they arrive." }];
    case "live":
      return hasLiveThreadActivity ? [] : [{ title: "Listening for agent events...", detail: "The stream is open and waiting for the first signal update." }];
    default:
      return [];
  }
}

export function useExperimentPlannerController(apiOverride?: ExperimentPlannerApi, streamOverride?: AgentStreamApi): ExperimentPlannerViewModel {
  const [state, dispatch] = useReducer(experimentPlannerReducer, initialExperimentPlannerState);
  const [composerQuestion, setComposerQuestion] = useState(stateQuestion(initialExperimentPlannerState));
  const [localUserMessages, setLocalUserMessages] = useState<ThreadLocalUserMessage[]>([]);
  const [isApproving, setIsApproving] = useState(false);
  const stateRef = useRef(state);
  const composerQuestionRef = useRef(composerQuestion);
  const streamRef = useRef<AgentStreamConnection | null>(null);
  const lastFileRef = useRef<File | null>(null);
  const lastImportRef = useRef<ImportCsvResponse | null>(null);
  const lastSignalRef = useRef<Signal | null>(null);
  const lastSignalsRef = useRef<Signal[]>([]);
  const lastHypothesesRef = useRef<Hypothesis[]>([]);
  const nextLocalSequenceRef = useRef(0);
  const api = useMemo(() => apiOverride ?? createFetchExperimentPlannerApi(), [apiOverride]);
  const streamApi = useMemo(() => streamOverride ?? createWebSocketAgentStreamApi(), [streamOverride]);
  stateRef.current = state;
  composerQuestionRef.current = composerQuestion;

  useEffect(() => {
    return () => {
      streamRef.current?.close();
    };
  }, []);

  // Restore a thread on mount: a specific one via ?thread=<id> (from the home
  // page conversation list), nothing for ?new (start a fresh conversation), or
  // the last-active thread otherwise (so a plain refresh survives). The backend
  // replays the committed history on reconnect.
  const restoredRef = useRef(false);
  const campaignIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    if (stateRef.current.thread.threadId) return;

    const params = new URLSearchParams(window.location.search);
    const campaignId = params.get("campaign");
    campaignIdRef.current = campaignId;

    let target: { threadId: string; streamUrl: string } | null = null;
    if (campaignId) {
      // A user campaign card: restore its bound thread if it has one, else stay
      // blank (the first message creates the thread and binds it).
      const camp = getCampaign(campaignId);
      if (camp?.threadId) {
        target = { threadId: camp.threadId, streamUrl: camp.streamUrl ?? agentThreadStreamUrl(camp.threadId) };
      }
    } else {
      // The demo campaign / plain planner: restore the last-active thread so a
      // refresh survives.
      target = readPersistedThread();
    }
    if (!target) return;
    dispatch({ type: "AGENT_SESSION_ACCEPTED", threadId: target.threadId, streamUrl: target.streamUrl });
    void connectStream(target.threadId, target.streamUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  async function connectStream(threadId: string, streamUrl: string) {
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
        threadId,
        streamUrl,
        onOpen: () => {
          dispatch({ type: "STREAM_CONNECTED" });
          settle(resolve);
        },
        onEvent: (streamMessage) => {
          dispatch({ type: "STREAM_EVENT_RECEIVED", message: streamMessage });
          const errorBlock = streamMessage.blocks.find((block) => block.kind === "error");
          if (errorBlock) {
            settle(() => reject(new Error(errorBlock.detail ?? errorBlock.title)));
          }
        },
        onError: (message) => {
          dispatch({ type: "STREAM_FAILED", threadId, message });
          settle(() => reject(new Error(message)));
        },
      });
    });
  }

  async function analyze() {
    const current = stateRef.current;
    if ((current.phase !== "input_ready" && current.phase !== "import_failed") || !current.composer.file) return;
    let requestPhase: "import" | "analysis" = "import";

    try {
      const importingState = experimentPlannerReducer(current, { type: "IMPORT_REQUESTED" });
      dispatch({ type: "IMPORT_REQUESTED" });
      if (importingState.phase !== "importing" || !importingState.composer.file) return;

      const importResult = await api.importCsv({
        file: importingState.composer.file,
        workspaceId: "demo_workspace",
        campaignId: "camp_comeback_teaser",
      });
      lastImportRef.current = importResult;
      requestPhase = "analysis";

      const importedState = experimentPlannerReducer(importingState, { type: "IMPORT_SUCCEEDED", importResult });
      dispatch({ type: "IMPORT_SUCCEEDED", importResult });
      if (!importedState.importResult) return;

      const startingState = experimentPlannerReducer(importedState, { type: "AGENT_SESSION_REQUESTED" });
      dispatch({ type: "AGENT_SESSION_REQUESTED" });
      if (startingState.phase !== "starting") return;

      const threadId = `thread_${importResult.import_id.replace(/^imp_/, "")}`;
      const streamUrl = agentThreadStreamUrl(threadId);
      dispatch({
        type: "AGENT_SESSION_ACCEPTED",
        threadId: threadId,
        streamUrl,
      });
      persistThread(threadId, streamUrl);
      bindThreadToCampaign(threadId);
      await connectStream(threadId, streamUrl);

      const content = csvPrompt(composerQuestionRef.current);
      const attachments = [csvAttachment(importResult, importingState.composer.file.name)];
      streamRef.current?.send({
        command_id: commandId("cmd_initial_analysis"),
        type: "message.send",
        thread_id: threadId,
        content,
        attachments,
        client_created_at: new Date().toISOString(),
      });
      setLocalUserMessages((messages) => [
        ...messages,
        {
          message_id: `msg_local_${Date.now()}`,
          role: "user",
          content,
          attachments,
          clientSequence: nextLocalSequence(),
          phaseAtSend: "live",
        },
      ]);
      composerQuestionRef.current = "";
      setComposerQuestion("");
      dispatch({ type: "UPDATE_QUESTION", question: "" });
    } catch (error) {
      dispatch({
        type: requestPhase === "import" ? "IMPORT_FAILED" : "AGENT_SESSION_FAILED",
        message: error instanceof Error ? error.message : requestPhase === "import" ? "Import failed." : "Analysis failed.",
      });
    }
  }

  async function startConversationThread() {
    const current = stateRef.current;
    if (current.thread.threadId) return current.thread.threadId;

    const requestedState = experimentPlannerReducer(current, { type: "AGENT_SESSION_REQUESTED" });
    dispatch({ type: "AGENT_SESSION_REQUESTED" });
    if (requestedState.phase !== "starting") return null;

    const threadId = `thread_chat_${Date.now()}`;
    const streamUrl = agentThreadStreamUrl(threadId);
    dispatch({
      type: "AGENT_SESSION_ACCEPTED",
      threadId,
      streamUrl,
    });
    persistThread(threadId, streamUrl);
    await connectStream(threadId, streamUrl);
    return threadId;
  }

  function nextLocalSequence() {
    const current = stateRef.current;
    const baseline = current.thread.lastReceivedSequence + 0.1;
    nextLocalSequenceRef.current = Math.max(nextLocalSequenceRef.current + 0.01, baseline);
    return nextLocalSequenceRef.current;
  }

  function bindThreadToCampaign(threadId: string) {
    // If this planner was opened from a user campaign card, bind the live thread
    // to that campaign so re-opening the card restores this conversation.
    if (campaignIdRef.current) {
      setCampaignThread(campaignIdRef.current, threadId, agentThreadStreamUrl(threadId), Date.now());
    }
  }

  async function attachCsv(file: File) {
    dispatch({ type: "SELECT_CSV", file });
  }

  async function sendCsvMessageOnThread(current: ExperimentPlannerState, file: File, text: string) {
    const threadId = current.thread.threadId;
    if (!threadId) return false;
    const content = csvPrompt(text);
    let attachments: MessageAttachment[] = [
      {
        kind: "csv_import",
        id: `pending_csv_${Date.now()}`,
        title: file.name,
        filename: file.name,
      },
    ];
    setLocalUserMessages((messages) => [
      ...messages,
      {
        message_id: `msg_local_${Date.now()}`,
        role: "user",
        content,
        attachments,
        clientSequence: nextLocalSequence(),
        phaseAtSend: current.phase,
      },
    ]);
    try {
      const importResult = await api.importCsv({ file, workspaceId: "demo_workspace", campaignId: "camp_comeback_teaser" });
      attachments = [csvAttachment(importResult, file.name)];
    } catch {
      // Ingestion failed; still let the agent analyze whatever baseline exists.
    }
    streamRef.current?.send({
      command_id: commandId("cmd_message"),
      type: "message.send",
      thread_id: threadId,
      content,
      attachments,
      client_created_at: new Date().toISOString(),
    });
    bindThreadToCampaign(threadId);
    composerQuestionRef.current = "";
    setComposerQuestion("");
    dispatch({ type: "UPDATE_QUESTION", question: "" });
    dispatch({ type: "CLEAR_SELECTED_CSV" });
    return true;
  }

  async function sendComposerMessage() {
    const text = composerQuestionRef.current.trim();
    const current = stateRef.current;

    if (current.phase === "input_ready" && current.composer.file) {
      void analyze();
      return;
    }

    if (current.composer.file && current.thread.threadId) {
      await sendCsvMessageOnThread(current, current.composer.file, text);
      return;
    }

    if (!text) return;

    const threadId = current.thread.threadId ?? (await startConversationThread());
    if (threadId) {
      streamRef.current?.send({
        command_id: commandId("cmd_message"),
        type: "message.send",
        thread_id: threadId,
        content: text,
        client_created_at: new Date().toISOString(),
      });
      bindThreadToCampaign(threadId);
    }

    setLocalUserMessages((messages) => [
      ...messages,
      {
        message_id: `msg_local_${Date.now()}`,
        role: "user",
        content: text,
        clientSequence: nextLocalSequence(),
        phaseAtSend: current.phase,
      },
    ]);
    composerQuestionRef.current = "";
    setComposerQuestion("");
    dispatch({ type: "UPDATE_QUESTION", question: "" });
  }

  function continueSignalReview() {
    const current = stateRef.current;
    if (current.phase !== "signal_review" || !current.thread.threadId) return;
    dispatch({ type: "SIGNAL_CONFIRMED" });
    streamRef.current?.send({
      command_id: commandId("cmd_continue"),
      type: "message.send",
      thread_id: current.thread.threadId,
      content: "Use this signal",
      client_created_at: new Date().toISOString(),
    });
  }

  async function approvePlan() {
    const current = stateRef.current;
    if (current.phase !== "awaiting_approval" || !current.thread.threadId || !current.review.payload || !current.review.approvalId) return;

    const approvingState = experimentPlannerReducer(current, { type: "APPROVE_SENT" });
    dispatch({ type: "APPROVE_SENT" });

    setIsApproving(true);
    try {
      const request = buildApprovalRequest({
        experimentPlanId: approvingState.review.payload?.experiment_plan.id ?? current.review.payload.experiment_plan.id,
        draftExperiments: approvingState.review.draftExperiments,
        selectedExperimentIds: approvingState.review.selectedExperimentIds,
      });
      streamRef.current?.send({
        command_id: commandId("cmd_approve"),
        type: "message.send",
        thread_id: approvingState.thread.threadId ?? current.thread.threadId,
        content: "Approve this experiment plan.",
        action: {
          name: "approve",
          target_id: approvingState.review.approvalId,
          payload: { final_experiments: request.final_experiments },
        },
        client_created_at: new Date().toISOString(),
      });
    } catch (error) {
      dispatch({ type: "APPROVE_FAILED", message: error instanceof Error ? error.message : "Approval failed." });
    }
  }

  function rejectApproval(reason = "User rejected the experiment plan.") {
    const current = stateRef.current;
    if (current.phase !== "awaiting_approval" || !current.thread.threadId) return;

    streamRef.current?.send({
      command_id: commandId("cmd_reject"),
      type: "message.send",
      thread_id: current.thread.threadId,
      content: reason,
      action: { name: "reject", target_id: current.review.approvalId },
      client_created_at: new Date().toISOString(),
    });
    dispatch({ type: "REJECT_SENT", reason });
  }

  async function cancelSession(reason = "User cancelled the agent session.") {
    const current = stateRef.current;
    if (!current.thread.threadId) return;

    streamRef.current?.send({
      command_id: commandId("cmd_cancel"),
      type: "message.send",
      thread_id: current.thread.threadId,
      content: reason,
      action: { name: "cancel", target_id: current.review.approvalId },
      client_created_at: new Date().toISOString(),
    });

    dispatch({ type: "CANCEL_SENT", reason });
  }

  function editExperiment(experimentId: string, title: string) {
    const current = stateRef.current;
    if (current.phase !== "awaiting_approval" || !current.thread.threadId || !current.review.payload) return;

    const draftExperiments = current.review.draftExperiments.map((experiment) => (experiment.id === experimentId ? { ...experiment, title } : experiment));
    streamRef.current?.send({
      command_id: commandId("cmd_update_payload"),
      type: "message.send",
      thread_id: current.thread.threadId,
      content: `Revise the experiment title to "${title}".`,
      action: {
        name: "revise_artifact",
        target_id: current.review.payload.experiment_plan.id,
        payload: { final_experiments: draftExperiments.filter((experiment) => current.review.selectedExperimentIds.includes(experiment.id)) },
      },
      client_created_at: new Date().toISOString(),
    });
    dispatch({ type: "EDIT_EXPERIMENT", experimentId, patch: { title } });
  }

  function toggleExperiment(experimentId: string) {
    const current = stateRef.current;
    if (current.phase !== "awaiting_approval") return;
    dispatch({ type: "TOGGLE_EXPERIMENT", experimentId });
  }

  function selectHypothesis(hypothesisId: string) {
    const current = stateRef.current;
    if (current.phase !== "awaiting_approval") return;
    dispatch({ type: "SELECT_HYPOTHESIS", hypothesisId });
  }

  useEffect(() => {
    if (!state.review.approving) {
      setIsApproving(false);
    }
  }, [state.review.approving]);

  const allHypotheses = currentHypotheses.length > 0 ? currentHypotheses : lastHypothesesRef.current;
  const selectedHypothesisId = state.review.selectedHypothesisId;
  const primaryHypothesis =
    (selectedHypothesisId ? allHypotheses.find((h) => h.id === selectedHypothesisId) : null) ??
    allHypotheses[0] ?? null;
  const primaryExperiment = draftExperiments(state)[0] ?? finalExperiments(state)[0] ?? null;
  const signalGate: GateReview | null = lastSignalRef.current
    ? {
        id: "signal",
        title: "Signal Review",
        status: state.phase === "signal_review" ? "active" : "complete",
        signal: lastSignalRef.current,
        actionLabel: state.phase === "signal_review" ? "Use this signal" : "Signal accepted",
      }
    : null;
  const approvalGate: GateReview | null =
    state.phase === "awaiting_approval" || state.phase === "approved"
      ? {
          id: "approval",
          title: "Experiment Approval",
          status: state.phase === "approved" ? "complete" : "active",
          hypothesis: primaryHypothesis,
          hypotheses: allHypotheses,
          selectedHypothesisId,
          experiment: primaryExperiment,
          actionLabel: state.phase === "approved" ? "Approved" : "Approve Experiments",
        }
      : null;
  const gates = [signalGate, approvalGate].filter((gate): gate is GateReview => gate !== null);
  const currentGate = gates.find((gate) => gate.status === "active") ?? null;
  const gateHistory = gates.filter((gate) => gate !== currentGate);
  const displayState = agentState(state);
  const currentImportOrLast = currentImportResult ?? lastImportRef.current;
  const currentMessages = [...messages(state), ...localUserMessages];
  const currentDocuments = documents(state);
  const currentObservations = observations(state);
  const currentDraftExperiments = draftExperiments(state);
  const currentFinalExperiments = finalExperiments(state);
  const currentApproval = approval(state);
  const currentApprovalSequence = state.review.approvalSequence;
  const currentCalendarEvents = calendarEvents(state);
  const currentAnalysisFallbackOutput =
    signalGate || currentDraftExperiments.length > 0 || currentApproval ? null : analysisFallbackOutputFromTimeline(timelineItems(state));
  const liveThreadActivity = currentMessages.length > 0 || currentDocuments.length > 0 || currentObservations.length > 0;
  const statusRows = buildStatusRows(state, currentImportOrLast, liveThreadActivity);
  const screen: PlannerScreenView = {
    mode: screenMode(state, displayState),
    intro:
      liveThreadActivity || statusRows.length > 0 || primaryExperiment || currentApproval || stateMessage(state)
        ? null
        : {
            title: "Find the signal in this campaign.",
            description: "Attach campaign metrics and add context to start the analysis session.",
          },
    statusRows,
    errorMessage: stateMessage(state),
  };
  const composer = composerFromState(state, displayState, currentQuestion, currentFile?.name ?? null);
  const progress: PlannerProgressView = {
    visible: displayState !== "idle" && displayState !== "selected",
    threadLabel: runShortId(state),
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
    approvalSequence: currentApprovalSequence,
    calendarEvents: currentCalendarEvents,
    errorMessage: stateMessage(state),
    stateLabel: progress.stateLabel,
  });
  const threadGroups = threadGroupsFromMessages(streamMessages);
  const threadItems = threadDisplayItemsFromProjection({ groups: threadGroups, gates, currentGate });
  const outputPanelItems = outputPanelItemsFromState({
    documents: currentDocuments,
    signalGate,
    analysisFallback: currentAnalysisFallbackOutput,
    approvalGate,
    draftExperiments: currentDraftExperiments,
    finalExperiments: currentFinalExperiments,
    approval: currentApproval,
    calendarEvents: currentCalendarEvents,
  });
  const thread: PlannerThreadView = {
    hasActivity: statusRows.length > 0 || liveThreadActivity || toolLogs(state).length > 0 || Boolean(primaryExperiment) || Boolean(currentApproval) || Boolean(stateMessage(state)),
    streamMessages,
    groups: threadGroups,
    items: threadItems,
    userMessages: currentMessages.filter((message) => message.role === "user"),
    assistantMessages: currentMessages.filter((message) => message.role === "assistant"),
    documents: currentDocuments,
    observations: currentObservations,
    toolLogs: toolLogs(state),
    timelineItems: timelineItems(state),
    primaryExperiment,
  };
  const inspector: PlannerInspectorView = {
    canToggle: outputPanelItems.length > 0 || Boolean(currentGate) || gateHistory.length > 0 || Boolean(currentApproval),
    activeGateKey: currentGate ? `${currentGate.id}:${currentGate.status}` : null,
    currentGate,
    history: gateHistory,
    outputs: outputPanelItems,
  };
  const approvalView: PlannerApprovalView = {
    canApprove: state.phase === "awaiting_approval" && state.review.selectedExperimentIds.length > 0 && !isApproving,
    isApproving,
    selectedExperimentIds: state.review.selectedExperimentIds,
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
      selectCsv: attachCsv,
      sendMessage: sendComposerMessage,
      analyze,
      continueSignalReview,
      editExperiment,
      toggleExperiment,
      selectHypothesis,
      approve: approvePlan,
      reject: rejectApproval,
      cancel: cancelSession,
      reset: () => {
        lastFileRef.current = null;
        lastImportRef.current = null;
        lastSignalRef.current = null;
        lastSignalsRef.current = [];
        lastHypothesesRef.current = [];
        nextLocalSequenceRef.current = 0;
        composerQuestionRef.current = stateQuestion(initialExperimentPlannerState);
        setComposerQuestion(stateQuestion(initialExperimentPlannerState));
        setLocalUserMessages([]);
        clearPersistedThread();
        dispatch({ type: "RESET" });
      },
    },
  };
}
