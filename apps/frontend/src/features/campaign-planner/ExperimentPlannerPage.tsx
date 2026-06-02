"use client";

import { ChangeEvent, CSSProperties, useEffect, useState } from "react";
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
  Target,
} from "lucide-react";
import { useExperimentPlannerController } from "@/features/campaign-planner/hooks/useExperimentPlannerController";
import type { ChecklistStep, GateReview } from "@/features/campaign-planner/hooks/useExperimentPlannerController";
import type { AgentDocument, AgentMessage, ExperimentItem, Hypothesis, Signal } from "@/features/campaign-planner/state/experimentPlannerTypes";

function statusLabel(agentState: string) {
  switch (agentState) {
    case "selected":
      return "CSV_SELECTED";
    case "importing":
      return "IMPORTING_CSV";
    case "processing":
      return "RUNNING_EVIDENCE_SEARCH";
    case "ready":
      return "WAITING_FOR_APPROVAL";
    case "approved":
      return "SUCCESS";
    case "error":
      return "FAILED";
    default:
      return "IDLE";
  }
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function confidenceLabel(value: string) {
  return value.replace("_", " ");
}

function runShortId(state: ReturnType<typeof useExperimentPlannerController>["state"]) {
  return "agentRunId" in state && state.agentRunId ? state.agentRunId.slice(-3) : "new";
}

type ExperimentPlannerView = ReturnType<typeof useExperimentPlannerController>;

type StreamDocument = AgentDocument;

function StreamingText({ text }: { text: string }) {
  const words = text.split(" ");

  return (
    <span className="streaming-text" aria-label={text}>
      {words.map((word, index) => (
        <span className="stream-word" style={{ "--word-index": index } as CSSProperties} aria-hidden="true" key={`${word}-${index}`}>
          {word}
        </span>
      ))}
    </span>
  );
}

function MarkdownDocument({ markdown }: { markdown: string }) {
  const blocks = markdown.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);

  return (
    <div className="markdown-document">
      {blocks.map((block, index) => {
        if (block.startsWith("## ")) return <h2 key={index}>{block.slice(3)}</h2>;
        if (block.startsWith("# ")) return <h1 key={index}>{block.slice(2)}</h1>;
        if (block.startsWith("- ")) {
          return (
            <ul key={index}>
              {block.split("\n").map((line) => (
                <li key={line}>{line.replace(/^-\s*/, "")}</li>
              ))}
            </ul>
          );
        }
        return <p key={index}>{block}</p>;
      })}
    </div>
  );
}

function StreamMessageBubble({ message }: { message: AgentMessage }) {
  return (
    <article className={`thread-message ${message.role}`}>
      {message.role === "assistant" ? <div className="message-avatar">LP</div> : null}
      <div className="message-bubble">
        <div className="message-meta">
          <strong>{message.role === "assistant" ? "LaunchPilot" : "You"}</strong>
          <span>Message</span>
        </div>
        <p>
          <StreamingText text={message.content} />
        </p>
      </div>
    </article>
  );
}

function StreamDocumentCard({ document, onOpen }: { document: StreamDocument; onOpen: (document: StreamDocument) => void }) {
  return (
    <article className="thread-message assistant compact">
      <div className="message-avatar">LP</div>
      <button className="message-bubble document-card" type="button" onClick={() => onOpen(document)}>
        <div className="message-meta">
          <strong>{document.title}</strong>
          <span>{document.kind.replaceAll("_", " ")}</span>
        </div>
        <p>{document.summary}</p>
      </button>
    </article>
  );
}

function Topbar({
  state,
  agentState,
  steps,
  inspectorOpen,
  onToggleInspector,
}: Pick<ExperimentPlannerView, "state"> & {
  agentState: ExperimentPlannerView["agentState"];
  steps: ChecklistStep[];
  inspectorOpen: boolean;
  onToggleInspector: () => void;
}) {
  return (
    <header className="topbar">
      <div className="topbar-context" aria-label="Current workspace">
        <span>Comeback Teaser</span>
      </div>
      <AgentRunProgress agentState={agentState} steps={steps} />
      <div className="account-tools">
        <button className="round-button" aria-label="Notifications">
          <Bell size={17} strokeWidth={1.8} />
        </button>
        <button className="credit-pill" type="button">
          <span>Run</span>
          <b>{runShortId(state)}</b>
        </button>
        <button className="avatar" aria-label="Profile">S</button>
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
      </div>
    </header>
  );
}

function readableAgentState(agentState: ExperimentPlannerView["agentState"]) {
  switch (agentState) {
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

function analyzeButtonLabel(agentState: ExperimentPlannerView["agentState"]) {
  switch (agentState) {
    case "importing":
      return "Importing";
    case "processing":
      return "Analyzing";
    default:
      return "Analyze";
  }
}

function AgentRunProgress({
  agentState,
  steps,
}: {
  agentState: ExperimentPlannerView["agentState"];
  steps: ChecklistStep[];
}) {
  const activeIndex = steps.findIndex((step) => step.status === "active");
  const completedCount = steps.filter((step) => step.status === "complete").length;
  const currentStep = steps[activeIndex >= 0 ? activeIndex : Math.min(completedCount, steps.length - 1)];

  return (
    <section className="agent-run-progress" aria-label="Agent run status">
      <div className="agent-run-summary">
        <div>
          <strong>{currentStep?.label ?? "Agent run"}</strong>
          <span>{readableAgentState(agentState)}</span>
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
  canAnalyze,
  primaryExperiment,
  onFileChange,
  onOpenDocument,
  onReviewSpec,
}: {
  view: ExperimentPlannerView;
  canAnalyze: boolean;
  primaryExperiment?: ExperimentItem;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onOpenDocument: (document: StreamDocument) => void;
  onReviewSpec: () => void;
}) {
  return (
    <section className="thread-panel" aria-label="Campaign agent thread" tabIndex={-1}>
      <div className="thread-scroll">
        <article className="thread-message assistant">
          <div className="message-avatar">LP</div>
          <div className="message-bubble">
            <div className="message-meta">
              <strong>LaunchPilot</strong>
              <span>{readableAgentState(view.agentState)}</span>
            </div>
            <h1>What should we test next week?</h1>
            <p>Attach campaign metrics and I will turn the evidence into editable experiments for Comeback Teaser.</p>
          </div>
        </article>

        {view.messages.map((message) => (
          <StreamMessageBubble key={message.message_id} message={message} />
        ))}

        {view.documents.map((document) => (
          <StreamDocumentCard key={document.document_id} document={document} onOpen={onOpenDocument} />
        ))}

        {view.errorMessage ? (
          <article className="thread-message assistant">
            <div className="message-avatar">LP</div>
            <div className="message-bubble">
              <div className="message-meta">
                <strong>Agent run</strong>
                <span>{statusLabel(view.agentState)}</span>
              </div>
              <p className="error-message">{view.errorMessage}</p>
            </div>
          </article>
        ) : null}

        {view.observations.map((observation) => (
          <article className="thread-message assistant compact" key={observation.id}>
            <div className="message-avatar">LP</div>
            <div className="message-bubble observation">
              <div className="message-meta">
                <strong>{observation.title}</strong>
                <span>{observation.kind}</span>
              </div>
              <p>
                <StreamingText text={observation.summary} />
              </p>
              {observation.evidence_refs && observation.evidence_refs.length > 0 ? <small>Evidence: {observation.evidence_refs.join(", ")}</small> : null}
            </div>
          </article>
        ))}

        {primaryExperiment ? (
          <article className="thread-message assistant">
            <div className="message-avatar">LP</div>
            <div className="message-bubble result">
              <div className="message-meta">
                <strong>Recommended experiment</strong>
                <span>{readableAgentState(view.agentState)}</span>
              </div>
              <h2>{primaryExperiment.title}</h2>
              <p>
                <StreamingText text={primaryExperiment.production_brief} />
              </p>
              <button className="secondary-button" type="button" onClick={onReviewSpec}>
                Review & edit campaign spec
              </button>
            </div>
          </article>
        ) : null}

        {view.approval ? (
          <article className="thread-message assistant">
            <div className="message-avatar">LP</div>
            <div className="message-bubble success">
              <div className="message-meta">
                <strong>Approval complete</strong>
                <span>Outputs created</span>
              </div>
              <p>
                Growth brief {view.approval.growth_brief_id} and {view.calendarEvents.length} calendar event
                {view.calendarEvents.length === 1 ? "" : "s"} are ready.
              </p>
            </div>
          </article>
        ) : null}
      </div>

      <div className="thread-composer">
        <input id="csv-input" type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={onFileChange} />
        <label className="composer-label" htmlFor="agent-question">Agent instructions</label>
        <textarea
          id="agent-question"
          className="composer-input"
          value={view.question}
          rows={2}
          disabled={view.agentState === "importing" || view.agentState === "processing"}
          onChange={(event) => view.commands.updateQuestion(event.target.value)}
        />
        <div className="composer-toolbar">
          <label className="composer-attach" htmlFor="csv-input" title="Attach CSV" aria-label="Attach CSV campaign metrics">
            <Paperclip size={18} strokeWidth={1.8} />
          </label>
          {view.currentFile ? (
            <span className="file-chip" id="file-name">{view.currentFile.name}</span>
          ) : (
            <span className="composer-hint" id="file-name">Attach campaign metrics CSV</span>
          )}
          <button
            className="primary-button"
            type="button"
            disabled={!canAnalyze || view.agentState === "importing" || view.agentState === "processing"}
            onClick={view.commands.analyze}
          >
            <Send size={16} strokeWidth={1.8} />
            {analyzeButtonLabel(view.agentState)}
          </button>
        </div>
      </div>
    </section>
  );
}

function GateSummary({ gate }: { gate: GateReview }) {
  if (gate.id === "import") {
    return (
      <span>
        {gate.importResult.indexed_count} rows indexed · {gate.importResult.failed_count} failed
      </span>
    );
  }

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
  if (gate.id === "import") {
    return (
      <div className="gate-body">
        <dl className="gate-metrics">
          <div>
            <dt>File</dt>
            <dd>{gate.fileName}</dd>
          </div>
          <div>
            <dt>Rows indexed</dt>
            <dd>{gate.importResult.indexed_count}</dd>
          </div>
          <div>
            <dt>Failed rows</dt>
            <dd>{gate.importResult.failed_count}</dd>
          </div>
          <div>
            <dt>Columns</dt>
            <dd>{gate.importResult.columns.length}</dd>
          </div>
        </dl>
        <div className="column-list" aria-label="Detected CSV columns">
          {gate.importResult.columns.map((column) => (
            <span key={column}>{column}</span>
          ))}
        </div>
        {gate.status === "active" ? (
          <button className="approve-button" type="button" onClick={view.commands.continueImportReview}>
            {gate.actionLabel}
          </button>
        ) : null}
      </div>
    );
  }

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
      {view.draftExperiments.slice(1).map((experiment) => (
        <article className="experiment-card" key={experiment.id}>
          <div className="card-topline">
            <span className={`channel ${experiment.channel}`}>{experiment.channel}</span>
            <span>{experiment.scheduled_at}</span>
          </div>
          <h3>{experiment.title}</h3>
          <p>{experiment.production_brief}</p>
        </article>
      ))}
      {view.approval ? (
        <div className="approval-receipt" tabIndex={-1}>
          <strong>Human approval processed</strong>
          <span>
            Approved: {view.finalExperiments[0]?.title ?? "experiment plan"}. Growth brief {view.approval.growth_brief_id} and{" "}
            {view.calendarEvents.length} calendar event{view.calendarEvents.length === 1 ? "" : "s"} created.
          </span>
        </div>
      ) : null}
      {gate.status === "active" ? (
        <button className={`approve-button${view.agentState === "approved" ? " approved" : ""}`} type="button" disabled={!canApprove} onClick={view.commands.approve}>
          {view.isApproving ? "Approving" : gate.actionLabel}
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
  document,
}: {
  view: ExperimentPlannerView;
  open: boolean;
  canApprove: boolean;
  document: StreamDocument | null;
}) {
  return (
    <aside className="inspector-panel" aria-label="Campaign work details" aria-hidden={!open} tabIndex={open ? -1 : undefined}>
      <div className="inspector-top">
        <div>
          <strong>{document ? "Stream Document" : "Gate Review"}</strong>
          <span>{document?.title ?? (view.currentGate ? view.currentGate.title : "Awaiting a decision point")}</span>
        </div>
      </div>

      <div className="inspector-content">
        {document ? (
          <article className="document-viewer" tabIndex={-1}>
            <MarkdownDocument markdown={document.content} />
          </article>
        ) : view.currentGate ? (
          <GateCard gate={view.currentGate} view={view} canApprove={canApprove} current />
        ) : (
          <article className="empty-card">
            <h2>No active gate</h2>
            <p>Attach campaign metrics and run Analyze. Each decision point will appear here for review.</p>
          </article>
        )}

        {view.gateHistory.length > 0 ? (
          <section className="inspector-section gate-history" aria-label="Gate history">
            <div className="section-title">
              <span>Gate history</span>
              <small>Read-only audit trail</small>
            </div>
            {view.gateHistory.map((gate) => (
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
  canAnalyze,
  primaryExperiment,
  onFileChange,
  onOpenDocument,
  onReviewSpec,
}: {
  view: ExperimentPlannerView;
  canAnalyze: boolean;
  primaryExperiment?: ExperimentItem;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onOpenDocument: (document: StreamDocument) => void;
  onReviewSpec: () => void;
}) {
  return (
    <section className="campaign-agent-workspace" aria-label="Campaign agent workspace">
      <ThreadPanel view={view} canAnalyze={canAnalyze} primaryExperiment={primaryExperiment} onFileChange={onFileChange} onOpenDocument={onOpenDocument} onReviewSpec={onReviewSpec} />
    </section>
  );
}

export function ExperimentPlannerPage() {
  const router = useRouter();
  const view = useExperimentPlannerController();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<StreamDocument | null>(null);
  const primaryExperiment = view.draftExperiments[0] ?? view.finalExperiments[0];
  const canAnalyze = view.agentState === "selected" && view.question.trim().length > 0;
  const canApprove = view.agentState === "ready" && view.draftExperiments.length > 0 && !view.isApproving;
  const campaignStatus = view.agentState === "approved" ? "Approved" : view.agentState === "ready" ? "Needs approval" : "Active";
  const currentGateKey = view.currentGate ? `${view.currentGate.id}:${view.currentGate.status}` : null;

  useEffect(() => {
    if (currentGateKey) {
      setSelectedDocument(null);
      setInspectorOpen(true);
    }
  }, [currentGateKey]);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) view.commands.selectCsv(file);
  }

  function handleReviewSpec() {
    setSelectedDocument(null);
    setInspectorOpen(true);
    window.setTimeout(() => document.querySelector<HTMLInputElement>("#experiment-title")?.focus(), 0);
  }

  function handleOpenDocument(document: StreamDocument) {
    setSelectedDocument(document);
    setInspectorOpen(true);
  }

  function focusWorkspace(selector: string) {
    const target = document.querySelector<HTMLElement>(selector);
    target?.scrollIntoView({ block: "nearest", inline: "nearest" });
    target?.focus({ preventScroll: true });
  }

  function handleOutputClick() {
    setInspectorOpen(true);
    window.setTimeout(() => focusWorkspace(view.approval ? ".approval-receipt" : ".gate-card"), 0);
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
                <strong>Comeback Teaser</strong>
                <small>{campaignStatus}</small>
              </div>
            </button>
            <div className="campaign-subnav" aria-label="Comeback Teaser views">
              <button className="nav-item child active" type="button" onClick={() => focusWorkspace(".thread-panel")}>
                <FlaskConical size={18} strokeWidth={1.8} />
                <span>Experiment Planner</span>
              </button>
              <button className="nav-item child" type="button" data-locked={!view.approval} title={view.approval ? "View created calendar events" : "Approve experiments to create calendar events"} onClick={handleOutputClick}>
                <CalendarDays size={18} strokeWidth={1.8} />
                <span>Calendar</span>
              </button>
              <button className="nav-item child" type="button" data-locked={!view.approval} title={view.approval ? "View created Growth Brief" : "Approve experiments to create a Growth Brief"} onClick={handleOutputClick}>
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
          state={view.state}
          agentState={view.agentState}
          steps={view.reasoningChecklist}
          inspectorOpen={inspectorOpen}
          onToggleInspector={() => setInspectorOpen((open) => !open)}
        />
        <CampaignAgentWorkspace
          view={view}
          canAnalyze={canAnalyze}
          primaryExperiment={primaryExperiment}
          onFileChange={handleFileChange}
          onOpenDocument={handleOpenDocument}
          onReviewSpec={handleReviewSpec}
        />
        <InspectorPanel
          view={view}
          open={inspectorOpen}
          canApprove={canApprove}
          document={selectedDocument}
        />
      </main>
    </div>
  );
}
