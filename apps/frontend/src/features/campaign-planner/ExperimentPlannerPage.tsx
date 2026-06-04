"use client";

import { ChangeEvent, CSSProperties, ReactNode, useEffect, useMemo, useRef, useState } from "react";
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
import type { GateReview, PlannerProgressView, StatusRow, StreamMessage, StreamMessageBlock } from "@/features/campaign-planner/hooks/useExperimentPlannerController";
import type { AgentDocument, ExperimentItem, Hypothesis, Signal } from "@/features/campaign-planner/state/experimentPlannerTypes";

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

function StreamMessageCard({
  message,
  onOpenDocument,
}: {
  message: StreamMessage;
  onOpenDocument: (document: StreamDocument) => void;
}) {
  if (message.role === "user") {
    const text = message.blocks
      .filter((block): block is Extract<StreamMessageBlock, { kind: "text" }> => block.kind === "text")
      .map((block) => block.text)
      .join("\n");

    return (
      <article className="thread-message user">
        <div className="message-bubble">
          <div className="message-meta">
            <strong>You</strong>
            <span>Message</span>
          </div>
          <p>{text}</p>
        </div>
      </article>
    );
  }

  return (
    <article className="thread-message assistant-flow-message">
      <div className="message-avatar">{message.role === "system" ? "!" : "LP"}</div>
      <div className="assistant-flow">
        <div className="assistant-flow-label">{message.role === "system" ? "System" : "LaunchPilot"}</div>
        <div className="assistant-timeline">
          {message.blocks.map((block, index) => (
            <StreamBlockRow key={`${message.id}:${index}`} block={block} onOpenDocument={onOpenDocument} />
          ))}
        </div>
      </div>
    </article>
  );
}

function StreamBlockRow({
  block,
  onOpenDocument,
}: {
  block: StreamMessageBlock;
  onOpenDocument: (document: StreamDocument) => void;
}) {
  switch (block.kind) {
    case "text":
      return <TimelineTextRow text={block.text} tone="text" />;
    case "activity":
      return <TimelineTextRow text={block.title} tone={block.status === "failed" ? "failed" : block.status === "done" ? "done" : "active"} />;
    case "markdown_document":
      return (
        <button className="timeline-chain-row document done" type="button" onClick={() => onOpenDocument(block.document)} aria-label={`Open ${block.title}`}>
          <span className="timeline-glyph" aria-hidden="true" />
          <span className="timeline-document-card">
            <FileText size={15} strokeWidth={1.8} />
            <span>Prepared {block.title.toLowerCase()}</span>
          </span>
        </button>
      );
    case "artifact":
      return <TimelineTextRow text={`${block.title}`} tone="done" />;
    case "approval":
      return <TimelineTextRow text={block.title} tone="active" />;
    case "result":
      return <TimelineTextRow text={block.detail ? `${block.title}. ${block.detail}` : block.title} tone="done" />;
    case "error":
      return <TimelineTextRow text={block.detail ? `${block.title}: ${block.detail}` : block.title} tone="failed" />;
  }
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
      {progress.visible ? <AgentSessionProgress progress={progress} /> : null}
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

function AgentSessionProgress({ progress }: { progress: PlannerProgressView }) {
  const steps = progress.steps;
  const activeIndex = steps.findIndex((step) => step.status === "active");
  const completedCount = steps.filter((step) => step.status === "complete").length;
  const currentStep = steps[activeIndex >= 0 ? activeIndex : Math.min(completedCount, steps.length - 1)];

  return (
    <section className="agent-session-progress" aria-label="Agent session status">
      <div className="agent-run-summary">
        <div>
          <strong>{currentStep?.label ?? "Agent session"}</strong>
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
        view.thread.streamMessages.length,
        view.screen.statusRows.length,
        view.screen.errorMessage ?? "",
        view.thread.primaryExperiment?.id ?? "",
        view.approval.receipt?.growth_brief_id ?? "",
      ].join(":"),
    [
      view.thread.streamMessages.length,
      view.screen.statusRows.length,
      view.screen.errorMessage,
      view.thread.primaryExperiment?.id,
      view.approval.receipt?.growth_brief_id,
    ]
  );

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "end", behavior: "auto" });
  }, [scrollKey]);

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

        {view.thread.streamMessages.map((message) => (
          <StreamMessageCard key={message.id} message={message} onOpenDocument={onOpenDocument} />
        ))}
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

        {activeDocument ? (
          <section className="inspector-section document-viewer" aria-label={documentDisplayTitle(activeDocument)}>
            <article className="markdown-document">
              <MarkdownContent markdown={activeDocument.content} />
            </article>
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

function MarkdownContent({ markdown }: { markdown: string }) {
  const lines = markdown.split("\n");
  const elements: ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length === 0) return;
    elements.push(
      <ul key={`list-${elements.length}`}>
        {listItems.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    );
    listItems = [];
  };

  lines.forEach((line, index) => {
    if (line.startsWith("## ")) {
      flushList();
      elements.push(<h2 key={index}>{line.slice(3)}</h2>);
      return;
    }
    if (line.startsWith("# ")) {
      flushList();
      elements.push(<h1 key={index}>{line.slice(2)}</h1>);
      return;
    }
    if (line.startsWith("- ")) {
      listItems.push(line.slice(2));
      return;
    }
    if (!line.trim()) {
      flushList();
      return;
    }
    flushList();
    elements.push(<p key={index}>{line}</p>);
  });
  flushList();

  return elements;
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
    const latestDocument = view.thread.documents.at(-1) ?? null;
    if (latestDocument && selectedDocument?.document_id !== latestDocument.document_id) {
      setSelectedDocument(latestDocument);
      setInspectorOpen(true);
    }
  }, [selectedDocument?.document_id, view.thread.documents]);

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
