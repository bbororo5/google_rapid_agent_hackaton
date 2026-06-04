"use client";

import { ChangeEvent, CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bell,
  CalendarDays,
  FileText,
  FolderOpen,
  FlaskConical,
  House,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Paperclip,
  RotateCcw,
  Send,
  Square,
  Target,
} from "lucide-react";
import { useExperimentPlannerController } from "@/features/campaign-planner/hooks/useExperimentPlannerController";
import type { GateReview, PlannerProgressView, StatusRow } from "@/features/campaign-planner/hooks/useExperimentPlannerController";
import type { AgentDocument, AgentMessage, AgentObservation, ExperimentItem, Hypothesis, Signal, ToolCallLog } from "@/features/campaign-planner/state/experimentPlannerTypes";

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function confidenceLabel(value: string) {
  return value.replace("_", " ");
}

type ExperimentPlannerView = ReturnType<typeof useExperimentPlannerController>;

type StreamDocument = AgentDocument;

function documentDisplayTitle(document: StreamDocument) {
  if (document.kind === "evidence_scan") return "Evidence notes";
  return document.title;
}

function toolDisplayName(toolName: string) {
  const labels: Record<string, string> = {
    query_metric_baseline: "metric baseline",
    search_content_posts: "supporting posts",
    search_team_notes: "team context",
  };

  if (labels[toolName]) return labels[toolName];

  return toolName
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function toolStatusLabel(tool: ToolCallLog) {
  if (tool.status === "FAILED" && tool.error_message) return `Could not check ${toolDisplayName(tool.tool_name)}: ${tool.error_message}`;
  if (tool.status === "FAILED") return `Could not check ${toolDisplayName(tool.tool_name)}`;
  if (tool.status === "SUCCESS" && tool.duration_ms !== null) return `Checked ${toolDisplayName(tool.tool_name)} in ${tool.duration_ms}ms`;
  if (tool.status === "SUCCESS") return `Checked ${toolDisplayName(tool.tool_name)}`;
  if (tool.status === "RUNNING") return `Checking ${toolDisplayName(tool.tool_name)}`;
  return `Queued ${toolDisplayName(tool.tool_name)}`;
}

function StreamingText({ text }: { text: string }) {
  const words = text.split(" ");

  return (
    <span className="streaming-text" aria-label={text}>
      {words.map((word, index) => (
        <span className="stream-word" style={{ "--word-index": index } as CSSProperties} key={`${word}-${index}`}>
          {word}
          {index === words.length - 1 ? "" : " "}
        </span>
      ))}
    </span>
  );
}

function UserMessageCard({ message }: { message: AgentMessage }) {
  return (
    <article className="thread-message user">
      <div className="message-bubble">
        <div className="message-meta">
          <strong>You</strong>
          <span>Message</span>
        </div>
        <p>{message.content}</p>
      </div>
    </article>
  );
}

function AssistantTextFlow({
  timelineItems,
  primaryExperiment,
  approval,
  calendarEvents,
  onOpenDocument,
}: {
  timelineItems: ExperimentPlannerView["thread"]["timelineItems"];
  primaryExperiment?: ExperimentItem;
  approval: ExperimentPlannerView["approval"]["receipt"];
  calendarEvents: ExperimentPlannerView["approval"]["calendarEvents"];
  onOpenDocument: (document: StreamDocument) => void;
}) {
  const finalLines = [
    primaryExperiment ? `I drafted a recommended experiment: ${primaryExperiment.title}. ${primaryExperiment.production_brief}` : null,
    approval ? `Approval complete. Growth brief ${approval.growth_brief_id} and ${calendarEvents.length} calendar event${calendarEvents.length === 1 ? "" : "s"} are ready.` : null,
  ].filter((line): line is string => Boolean(line));

  if (timelineItems.length === 0 && finalLines.length === 0) return null;

  return (
    <article className="thread-message assistant-flow-message">
      <div className="message-avatar">LP</div>
      <div className="assistant-flow">
        <div className="assistant-flow-label">LaunchPilot</div>
        <div className="assistant-timeline">
          {timelineItems.map((item) => (
            <TimelineItemRow key={item.id} item={item} onOpenDocument={onOpenDocument} />
          ))}
          {finalLines.map((line, index) => (
            <TimelineTextRow key={`${line}-${index}`} text={line} tone="text" />
          ))}
        </div>
      </div>
    </article>
  );
}

function TimelineItemRow({
  item,
  onOpenDocument,
}: {
  item: ExperimentPlannerView["thread"]["timelineItems"][number];
  onOpenDocument: (document: StreamDocument) => void;
}) {
  if (item.kind === "tool") {
    return (
      <TimelineTextRow text={toolStatusLabel(item.tool)} tone={item.tool.status === "FAILED" ? "failed" : item.tool.status === "SUCCESS" ? "done" : "active"} />
    );
  }

  if (item.kind === "document") {
    return (
      <button className="timeline-chain-row document done" type="button" onClick={() => onOpenDocument(item.document)} aria-label={`Open ${documentDisplayTitle(item.document)}`}>
        <span className="timeline-glyph" aria-hidden="true" />
        <span className="timeline-document-card">Prepared {documentDisplayTitle(item.document).toLowerCase()}</span>
      </button>
    );
  }

  if (item.kind === "observation") {
    return <TimelineObservationBlock observation={item.observation} />;
  }

  return <TimelineTextRow text={item.message.content} tone="text" />;
}

function TimelineObservationBlock({ observation }: { observation: AgentObservation }) {
  return (
    <section className={`timeline-observation-block ${observation.kind}`} aria-label={observation.title}>
      <div className="timeline-observation-copy">
        <p>
          <StreamingText text={observation.summary} />
        </p>
      </div>
    </section>
  );
}

function TimelineTextRow({ text, tone }: { text: string; tone: "text" | "active" | "done" | "failed" }) {
  return (
    <p className={`timeline-chain-row ${tone}`}>
      <span className="timeline-glyph" aria-hidden="true" />
      <span>
        <StreamingText text={text} />
      </span>
    </p>
  );
}

function SystemStatusRows({ statuses }: { statuses: StatusRow[] }) {
  if (statuses.length === 0) return null;

  return (
    <div className="system-status-list" aria-label="System progress">
      {statuses.map((status) => (
        <div className="system-status-row" key={status.title}>
          <span className="status-pulse" aria-hidden="true" />
          <div>
            <strong>{status.title}</strong>
            <p>{status.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function Topbar({
  campaignName,
  progress,
  inspectorOpen,
  canToggleInspector,
  onToggleInspector,
}: {
  campaignName: string;
  progress: PlannerProgressView;
  inspectorOpen: boolean;
  canToggleInspector: boolean;
  onToggleInspector: () => void;
}) {
  return (
    <header className={`topbar${progress.visible ? "" : " no-progress"}`}>
      <div className="topbar-context" aria-label="Current workspace">
        <span>{campaignName}</span>
      </div>
      {progress.visible ? <AgentRunProgress progress={progress} /> : null}
      <div className="account-tools">
        <button className="round-button" aria-label="Notifications">
          <Bell size={17} strokeWidth={1.8} />
        </button>
        {progress.runLabel ? (
          <button className="credit-pill" type="button">
            <span>Run</span>
            <b>{progress.runLabel}</b>
          </button>
        ) : null}
        <button className="avatar" aria-label="Profile">S</button>
        {canToggleInspector ? (
          <button
            className={`round-button view-toggle${inspectorOpen ? " active" : ""}`}
            type="button"
            aria-label={inspectorOpen ? "Hide details panel" : "Show details panel"}
            aria-pressed={inspectorOpen}
            title={inspectorOpen ? "Hide details" : "Show details"}
            onClick={onToggleInspector}
          >
            {inspectorOpen ? <PanelRightClose size={17} strokeWidth={1.8} /> : <PanelRightOpen size={17} strokeWidth={1.8} />}
          </button>
        ) : null}
      </div>
    </header>
  );
}

function AgentRunProgress({ progress }: { progress: PlannerProgressView }) {
  const steps = progress.steps;
  const activeIndex = steps.findIndex((step) => step.status === "active");
  const completedCount = steps.filter((step) => step.status === "complete").length;
  const currentStep = steps[activeIndex >= 0 ? activeIndex : Math.min(completedCount, steps.length - 1)];

  return (
    <section className="agent-run-progress" aria-label="Agent run status">
      <div className="agent-run-summary">
        <div>
          <strong>{currentStep?.label ?? "Agent run"}</strong>
          <span>{progress.stateLabel}</span>
        </div>
        <span className="run-progress-count">
          {Math.min(completedCount + (activeIndex >= 0 ? 1 : 0), steps.length)} / {steps.length}
        </span>
      </div>
      <div className="run-step-strip" aria-label="Agent reasoning progress">
        {steps.map((step) => (
          <span key={step.label} className={step.status} title={`${step.label}: ${step.status}`}>
            {step.label}
          </span>
        ))}
      </div>
    </section>
  );
}

function SignalCard({ signal, primary = false }: { signal: Signal; primary?: boolean }) {
  return (
    <article className={`signal-card${primary ? " primary" : ""}`}>
      <div className="card-topline">
        <span className={`status-pill ${signal.confidence === "high" ? "high" : "medium"}`}>{confidenceLabel(signal.confidence)}</span>
        <span>
          {signal.metric_name} · {signal.lift_ratio.toFixed(1)}x
        </span>
      </div>
      <h2>{signal.title}</h2>
      <p>{signal.description}</p>
      <div className="metric-row">
        <span>
          <b>{formatPercent(signal.current_value)}</b>
          current
        </span>
        <span>
          <b>{formatPercent(signal.baseline_value)}</b>
          baseline
        </span>
        <span>
          <b>{signal.evidence_refs.length} refs</b>
          grounded
        </span>
      </div>
    </article>
  );
}

function HypothesisCard({ hypothesis }: { hypothesis: Hypothesis }) {
  return (
    <article className="hypothesis-card">
      <div className="section-title compact">
        <span>Hypothesis</span>
        <small>Generated from signal and evidence refs</small>
      </div>
      <blockquote>{hypothesis.statement}</blockquote>
      <p>{hypothesis.rationale}</p>
      <ul>
        <li>Evidence: {hypothesis.supporting_evidence_refs.join(", ")}</li>
        {hypothesis.caveats.map((caveat) => (
          <li key={caveat}>Caveat: {caveat}</li>
        ))}
      </ul>
    </article>
  );
}

function ExperimentEditor({
  experiment,
  onEdit,
}: {
  experiment: ExperimentItem;
  onEdit: (experimentId: string, title: string) => void;
}) {
  return (
    <article className="experiment-card selected">
      <div className="card-topline">
        <span className={`channel ${experiment.channel}`}>{experiment.channel}</span>
        <span>{experiment.scheduled_at}</span>
      </div>
      <h3>{experiment.title}</h3>
      <label htmlFor="experiment-title">Experiment title</label>
      <input id="experiment-title" type="text" value={experiment.title} onChange={(event) => onEdit(experiment.id, event.target.value)} />
      <dl>
        <div>
          <dt>Hook</dt>
          <dd>{experiment.hook}</dd>
        </div>
        <div>
          <dt>CTA</dt>
          <dd>{experiment.cta}</dd>
        </div>
        <div>
          <dt>Success criteria</dt>
          <dd>{experiment.success_criteria}</dd>
        </div>
      </dl>
    </article>
  );
}

function ThreadPanel({
  view,
  onFileChange,
  onOpenDocument,
}: {
  view: ExperimentPlannerView;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onOpenDocument: (document: StreamDocument) => void;
}) {
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const scrollKey = useMemo(
    () =>
      [
        view.thread.userMessages.length,
        view.thread.timelineItems.length,
        view.screen.statusRows.length,
        view.screen.errorMessage ?? "",
        view.thread.primaryExperiment?.id ?? "",
        view.approval.receipt?.growth_brief_id ?? "",
      ].join(":"),
    [
      view.thread.userMessages.length,
      view.thread.timelineItems.length,
      view.screen.statusRows.length,
      view.screen.errorMessage,
      view.thread.primaryExperiment?.id,
      view.approval.receipt?.growth_brief_id,
    ]
  );

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "end", behavior: "auto" });
  }, [scrollKey]);

  const initialUserMessages = view.thread.userMessages.filter((message) => !message.message_id.startsWith("msg_local_"));
  const localUserMessages = view.thread.userMessages.filter((message) => message.message_id.startsWith("msg_local_"));

  const handleComposerPrimaryAction = () => {
    switch (view.composer.primaryAction.kind) {
      case "analyze":
      case "retry":
        void view.commands.analyze();
        return;
      case "send":
        view.commands.sendMessage();
        return;
      case "stop":
        void view.commands.cancel();
        return;
      case "new_run":
      case "none":
        return;
    }
  };

  return (
    <section className={`thread-panel${view.thread.hasActivity ? "" : " empty-thread"}`} aria-label="Campaign agent thread" tabIndex={-1}>
      <div className="thread-scroll">
        {view.screen.intro ? (
          <div className="thread-empty-intro" aria-label="LaunchPilot prompt">
            <h1>{view.screen.intro.title}</h1>
            <p>{view.screen.intro.description}</p>
          </div>
        ) : null}

        <SystemStatusRows statuses={view.screen.statusRows} />

        {initialUserMessages.map((message) => (
          <UserMessageCard key={message.message_id} message={message} />
        ))}

        <AssistantTextFlow
          timelineItems={view.thread.timelineItems}
          primaryExperiment={view.thread.primaryExperiment ?? undefined}
          approval={view.approval.receipt}
          calendarEvents={view.approval.calendarEvents}
          onOpenDocument={onOpenDocument}
        />

        {localUserMessages.map((message) => (
          <UserMessageCard key={message.message_id} message={message} />
        ))}

        {view.screen.errorMessage ? (
          <article className="thread-message assistant-flow-message">
            <div className="message-avatar">LP</div>
            <div className="assistant-flow">
              <div className="assistant-flow-label">Agent run · {view.progress.stateLabel}</div>
              <p className="error-message">{view.screen.errorMessage}</p>
            </div>
          </article>
        ) : null}
        <div className="thread-scroll-anchor" ref={threadEndRef} aria-hidden="true" />
      </div>

      <div className="thread-composer">
        <input id="csv-input" type="file" accept=".csv,text/csv" aria-label="CSV file" disabled={!view.composer.canAttachCsv} onChange={onFileChange} />
        <label className="composer-label" htmlFor="agent-question">Agent instructions</label>
        <textarea
          id="agent-question"
          className="composer-input"
          value={view.composer.value}
          placeholder={view.composer.placeholder}
          rows={2}
          disabled={view.composer.inputDisabled}
          onChange={(event) => view.commands.updateQuestion(event.target.value)}
        />
        <div className="composer-toolbar">
          <label
            className={`composer-attach${view.composer.fileName ? "" : " empty"}${view.composer.canAttachCsv ? "" : " disabled"}`}
            htmlFor="csv-input"
            title={view.composer.fileName ? "Replace CSV" : "Attach CSV"}
            aria-label={view.composer.fileName ? "Replace CSV campaign metrics" : "Attach CSV campaign metrics"}
          >
            <Paperclip size={18} strokeWidth={1.8} />
            {view.composer.fileName ? null : <span>Attach campaign metrics CSV</span>}
          </label>
          {view.composer.fileName ? (
            <span className="file-chip" id="file-name">{view.composer.fileName}</span>
          ) : null}
          {view.composer.primaryAction.kind !== "none" ? (
            <button
              className={`primary-button composer-action-${view.composer.primaryAction.kind}`}
              type="button"
              disabled={view.composer.primaryAction.disabled}
              title={view.composer.primaryAction.title}
              onClick={handleComposerPrimaryAction}
            >
              {view.composer.primaryAction.kind === "stop" ? <Square size={14} strokeWidth={2.1} fill="currentColor" /> : <Send size={16} strokeWidth={1.8} />}
              {view.composer.primaryAction.label}
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function GateSummary({ gate }: { gate: GateReview }) {
  if (gate.id === "signal") {
    return (
      <span>
        {gate.signal.metric_name} · {gate.signal.lift_ratio.toFixed(1)}x · {confidenceLabel(gate.signal.confidence)}
      </span>
    );
  }

  return <span>{gate.experiment ? gate.experiment.title : "Experiment plan"}</span>;
}

function GateContent({
  gate,
  view,
  canApprove,
}: {
  gate: GateReview;
  view: ExperimentPlannerView;
  canApprove: boolean;
}) {
  if (gate.id === "signal") {
    return (
      <div className="gate-body">
        <SignalCard signal={gate.signal} primary />
        <dl className="gate-metrics">
          <div>
            <dt>Metric</dt>
            <dd>{gate.signal.metric_name}</dd>
          </div>
          <div>
            <dt>Current</dt>
            <dd>{formatPercent(gate.signal.current_value)}</dd>
          </div>
          <div>
            <dt>Baseline</dt>
            <dd>{formatPercent(gate.signal.baseline_value)}</dd>
          </div>
          <div>
            <dt>Lift</dt>
            <dd>{gate.signal.lift_ratio.toFixed(1)}x</dd>
          </div>
        </dl>
        {gate.status === "active" ? (
          <button className="approve-button" type="button" onClick={view.commands.continueSignalReview}>
            {gate.actionLabel}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="gate-body">
      {gate.hypothesis ? <HypothesisCard hypothesis={gate.hypothesis} /> : null}
      {gate.experiment ? <ExperimentEditor experiment={gate.experiment} onEdit={view.commands.editExperiment} /> : null}
      {view.approval.draftExperiments.slice(1).map((experiment) => (
        <article className="experiment-card" key={experiment.id}>
          <div className="card-topline">
            <span className={`channel ${experiment.channel}`}>{experiment.channel}</span>
            <span>{experiment.scheduled_at}</span>
          </div>
          <h3>{experiment.title}</h3>
          <p>{experiment.production_brief}</p>
        </article>
      ))}
      {view.approval.receipt ? (
        <div className="approval-receipt" tabIndex={-1}>
          <strong>Human approval processed</strong>
          <span>
            Approved: {view.approval.finalExperiments[0]?.title ?? "experiment plan"}. Growth brief {view.approval.receipt.growth_brief_id} and{" "}
            {view.approval.calendarEvents.length} calendar event{view.approval.calendarEvents.length === 1 ? "" : "s"} created.
          </span>
        </div>
      ) : null}
      {gate.status === "active" ? (
        <button className={`approve-button${view.shell.campaignStatus === "approved" ? " approved" : ""}`} type="button" disabled={!canApprove} onClick={view.commands.approve}>
          {view.approval.isApproving ? "Approving" : gate.actionLabel}
        </button>
      ) : null}
    </div>
  );
}

function GateCard({
  gate,
  view,
  canApprove,
  current = false,
}: {
  gate: GateReview;
  view: ExperimentPlannerView;
  canApprove: boolean;
  current?: boolean;
}) {
  return (
    <details className={`gate-card ${gate.status}`} open={current}>
      <summary>
        <div>
          <strong>{gate.title}</strong>
          <GateSummary gate={gate} />
        </div>
        <small>{gate.status === "active" ? "Current gate" : "Completed"}</small>
      </summary>
      <GateContent gate={gate} view={view} canApprove={canApprove} />
    </details>
  );
}

function InspectorPanel({
  view,
  open,
  canApprove,
  selectedDocument,
  onSelectDocument,
}: {
  view: ExperimentPlannerView;
  open: boolean;
  canApprove: boolean;
  selectedDocument: StreamDocument | null;
  onSelectDocument: (document: StreamDocument) => void;
}) {
  const documents = view.thread.documents;
  const activeDocument = selectedDocument ?? documents[0] ?? null;

  return (
    <aside className="inspector-panel" aria-label="Campaign work details" aria-hidden={!open} tabIndex={open ? -1 : undefined}>
      <div className="inspector-top">
        <div>
          <strong>Work Review</strong>
          <span>{view.inspector.currentGate ? view.inspector.currentGate.title : activeDocument ? documentDisplayTitle(activeDocument) : "Awaiting a decision point"}</span>
        </div>
      </div>

      <div className="inspector-content">
        {documents.length > 0 ? (
          <section className="inspector-section document-list-section" aria-label="Stream documents">
            <div className="section-title">
              <span>Documents</span>
              <small>{documents.length} output{documents.length === 1 ? "" : "s"}</small>
            </div>
            <div className="document-list" role="list">
              {documents.map((streamDocument) => {
                const selected = activeDocument?.document_id === streamDocument.document_id;

                return (
                  <button
                    className={`document-list-item${selected ? " selected" : ""}`}
                    type="button"
                    aria-current={selected ? "true" : undefined}
                    key={streamDocument.document_id}
                    onClick={() => onSelectDocument(streamDocument)}
                  >
                    <FileText size={17} strokeWidth={1.8} />
                    <span>
                      <strong>{documentDisplayTitle(streamDocument)}</strong>
                      <small>{streamDocument.kind.replaceAll("_", " ")}</small>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        {view.inspector.currentGate ? (
          <section className="inspector-section" aria-label="Current decision">
            <div className="section-title">
              <span>Current decision</span>
              <small>Continue the run</small>
            </div>
            <GateCard gate={view.inspector.currentGate} view={view} canApprove={canApprove} current />
          </section>
        ) : !activeDocument ? (
          <article className="empty-card">
            <h2>No active gate</h2>
            <p>Attach campaign metrics and send context. Decisions and generated documents will appear here for review.</p>
          </article>
        ) : null}

        {view.inspector.history.length > 0 ? (
          <section className="inspector-section gate-history" aria-label="Gate history">
            <div className="section-title">
              <span>Gate history</span>
              <small>Read-only audit trail</small>
            </div>
            {view.inspector.history.map((gate) => (
              <GateCard key={gate.id} gate={gate} view={view} canApprove={canApprove} />
            ))}
          </section>
        ) : null}
      </div>
    </aside>
  );
}

function CampaignAgentWorkspace({
  view,
  onFileChange,
  onOpenDocument,
}: {
  view: ExperimentPlannerView;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onOpenDocument: (document: StreamDocument) => void;
}) {
  return (
    <section className="campaign-agent-workspace" aria-label="Campaign agent workspace">
      <ThreadPanel view={view} onFileChange={onFileChange} onOpenDocument={onOpenDocument} />
    </section>
  );
}

export function ExperimentPlannerPage() {
  const router = useRouter();
  const view = useExperimentPlannerController();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<StreamDocument | null>(null);
  const campaignStatus = view.shell.campaignStatus === "approved" ? "Approved" : view.shell.campaignStatus === "needs_review" ? "Needs approval" : view.shell.campaignStatus === "error" ? "Needs attention" : "Active";
  const canToggleInspector = inspectorOpen || view.thread.documents.length > 0 || view.inspector.canToggle;

  useEffect(() => {
    if (view.inspector.activeGateKey) {
      setInspectorOpen(true);
    }
  }, [view.inspector.activeGateKey]);

  useEffect(() => {
    if (!selectedDocument && view.thread.documents.length > 0) {
      setSelectedDocument(view.thread.documents[0]);
    }
  }, [selectedDocument, view.thread.documents]);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) view.commands.selectCsv(file);
  }

  function handleOpenDocument(streamDocument: StreamDocument) {
    setSelectedDocument(streamDocument);
    setInspectorOpen(true);
    window.setTimeout(() => focusWorkspace(".document-list-section"), 0);
  }

  function focusWorkspace(selector: string) {
    const target = document.querySelector<HTMLElement>(selector);
    target?.scrollIntoView({ block: "nearest", inline: "nearest" });
    target?.focus({ preventScroll: true });
  }

  function handleOutputClick() {
    setInspectorOpen(true);
    window.setTimeout(() => focusWorkspace(view.approval.receipt ? ".approval-receipt" : ".gate-card"), 0);
  }

  return (
    <div className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar-shell" aria-label="LaunchPilot navigation">
        <header className="sidebar-top">
          <div className="brand">
            <span className="brand-mark">LP</span>
            <span className="brand-word">LaunchPilot</span>
          </div>
          <div className="top-actions">
            <button
              className="icon-button"
              aria-label="Toggle sidebar"
              aria-pressed={sidebarCollapsed}
              title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={18} strokeWidth={1.8} /> : <PanelLeftClose size={18} strokeWidth={1.8} />}
            </button>
          </div>
        </header>

        <nav className="nav-list" aria-label="Workspace navigation">
          <button className="nav-item parent" type="button" onClick={() => router.push("/")}>
            <FolderOpen size={18} strokeWidth={1.8} />
            <span>Campaigns</span>
          </button>

          <section className="project-section" aria-label="Current campaign">
            <button className="campaign-card" type="button" onClick={() => focusWorkspace(".thread-panel")}>
              <div className="side-icon">
                <Target size={18} strokeWidth={1.8} />
              </div>
              <div className="side-row-label">
                <strong>{view.shell.campaignName}</strong>
                <small>{campaignStatus}</small>
              </div>
            </button>
            <div className="campaign-subnav" aria-label="Comeback Teaser views">
              <button className="nav-item child active" type="button" onClick={() => focusWorkspace(".thread-panel")}>
                <FlaskConical size={18} strokeWidth={1.8} />
                <span>Experiment Planner</span>
              </button>
              <button className="nav-item child" type="button" data-locked={!view.approval.receipt} title={view.approval.receipt ? "View created calendar events" : "Approve experiments to create calendar events"} onClick={handleOutputClick}>
                <CalendarDays size={18} strokeWidth={1.8} />
                <span>Calendar</span>
              </button>
              <button className="nav-item child" type="button" data-locked={!view.approval.receipt} title={view.approval.receipt ? "View created Growth Brief" : "Approve experiments to create a Growth Brief"} onClick={handleOutputClick}>
                <FileText size={18} strokeWidth={1.8} />
                <span>Briefs</span>
              </button>
            </div>
          </section>
        </nav>

        <div className="sidebar-spacer" />

        <footer className="sidebar-footer">
          <button className="icon-button" aria-label="Back to campaigns" title="Back to campaigns" onClick={() => router.push("/")}>
            <House size={18} strokeWidth={1.8} />
          </button>
          <button className="icon-button reset-button" aria-label="Reset demo" title="Reset demo" onClick={view.commands.reset}>
            <RotateCcw size={18} strokeWidth={1.8} />
            <span>Reset demo</span>
          </button>
        </footer>
      </aside>

      <main className={`main-shell${inspectorOpen ? " inspector-open" : " inspector-closed"}`}>
        <Topbar
          campaignName={view.shell.campaignName}
          progress={view.progress}
          inspectorOpen={inspectorOpen}
          canToggleInspector={canToggleInspector}
          onToggleInspector={() => setInspectorOpen((open) => !open)}
        />
        <CampaignAgentWorkspace
          view={view}
          onFileChange={handleFileChange}
          onOpenDocument={handleOpenDocument}
        />
        <InspectorPanel
          view={view}
          open={inspectorOpen}
          canApprove={view.approval.canApprove}
          selectedDocument={selectedDocument}
          onSelectDocument={handleOpenDocument}
        />
      </main>
    </div>
  );
}
