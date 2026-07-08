"use client";

import { ChangeEvent, CSSProperties, KeyboardEvent, ReactNode, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
  X,
} from "lucide-react";
import { useExperimentPlannerController } from "@/features/campaign-planner/hooks/useExperimentPlannerController";
import type { GateReview, OutputPanelItem, PlannerProgressView, StatusRow, StreamMessageBlock, ThreadDisplayItem, ThreadMessageGroup } from "@/features/campaign-planner/hooks/useExperimentPlannerController";
import type { AgentDocument, ExperimentItem, Hypothesis, Signal } from "@/features/campaign-planner/state/experimentPlannerTypes";

// Contract 01 Signal has no unit field: rate-style metrics (0..1) render as
// percentages, count metrics (views, shares, ...) as plain numbers.
function formatMetricValue(metricName: string, value: number) {
  if (/(_rate|_ratio|_pct)$/.test(metricName)) {
    return `${(value * 100).toFixed(1)}%`;
  }
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

function confidenceLabel(value: string) {
  return value.replace("_", " ");
}

type ExperimentPlannerView = ReturnType<typeof useExperimentPlannerController>;

type StreamDocument = AgentDocument;

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
  if (tone === "text") {
    return (
      <div className={`timeline-chain-row ${tone}`}>
        <span className="timeline-glyph" aria-hidden="true" />
        <div className="timeline-markdown">
          <MarkdownContent markdown={normalizeAssistantMarkdown(text)} />
        </div>
      </div>
    );
  }

  return (
    <p className={`timeline-chain-row ${tone}`}>
      <span className="timeline-glyph" aria-hidden="true" />
      <span>
        <StreamingText text={text} />
      </span>
    </p>
  );
}

function activityTarget(title: string) {
  return title
    .replace(/^Checking\s+/i, "")
    .replace(/^Checked\s+/i, "")
    .replace(/^Loading\s+/i, "")
    .replace(/^Loaded\s+/i, "")
    .replace(/^Resolving\s+/i, "")
    .replace(/^Resolved\s+/i, "")
    .replace(/^Interpreting\s+/i, "")
    .replace(/^Interpreted\s+/i, "")
    .replace(/^Applying\s+/i, "")
    .replace(/^Applied\s+/i, "")
    .replace(/^Starting\s+/i, "")
    .replace(/^Finished\s+/i, "")
    .replace(/^Preparing\s+/i, "")
    .replace(/^Prepared\s+/i, "")
    .replace(/^Drafting\s+/i, "")
    .replace(/^Drafted\s+/i, "")
    .replace(/^Saving\s+/i, "")
    .replace(/^Saved\s+/i, "")
    .replace(/^Queued\s+/i, "")
    .replace(/^Could not check\s+/i, "")
    .replace(/\s+in\s+\d+ms$/i, "")
    // Korean progress titles pair as "<대상> ... 중" (running) / "<대상> ... 완료" (done);
    // strip the trailing status word so both map to the same dedup key.
    .replace(/\s*(시작|중|완료|실패|통과|없음)$/, "")
    .trim()
    .toLowerCase();
}

function compactActivityBlocks(blocks: Extract<StreamMessageBlock, { kind: "activity" }>[]) {
  // Key by the stable progress id first: running/done pairs always share an id,
  // so dedup survives title wording changes. Title heuristic is the fallback.
  return [...blocks.reduce((latest, block) => latest.set(block.id || activityTarget(block.title) || block.title, block), new Map<string, Extract<StreamMessageBlock, { kind: "activity" }> >()).values()];
}

function toolSummary(blocks: Extract<StreamMessageBlock, { kind: "activity" }>[]) {
  const failed = blocks.filter((block) => block.status === "failed").length;
  const running = blocks.filter((block) => block.status === "running" || block.status === "queued").length;
  const done = blocks.filter((block) => block.status === "done").length;

  if (failed > 0) return `도구 확인 ${failed}건 주의 필요`;
  if (running > 0) return `도구 확인 ${running}건 실행 중`;
  return `도구 확인 ${done}건 완료`;
}

function ActivitySummary({ blocks }: { blocks: Extract<StreamMessageBlock, { kind: "activity" }>[] }) {
  const compactedBlocks = compactActivityBlocks(blocks);
  if (compactedBlocks.length === 0) return null;
  const hasRunning = compactedBlocks.some((block) => block.status === "running" || block.status === "queued");

  return (
    <details className={`tool-summary${hasRunning ? " running" : ""}`} open={hasRunning}>
      <summary>
        <span className="timeline-glyph" aria-hidden="true" />
        <span>
          {toolSummary(compactedBlocks)}
          {hasRunning ? <b className="tool-live-label">실시간</b> : null}
        </span>
      </summary>
      <div className="tool-summary-list">
        {compactedBlocks.map((block) => (
          <span className={block.status} key={block.id}>
            <b>{block.title}</b>
            {block.detail ? <small>{block.detail}</small> : null}
          </span>
        ))}
      </div>
    </details>
  );
}

function StreamBlockSequence({
  groupId,
  blocks,
  onOpenDocument,
}: {
  groupId: string;
  blocks: StreamMessageBlock[];
  onOpenDocument: (document: StreamDocument) => void;
}) {
  const rows: ReactNode[] = [];
  let activityRun: Extract<StreamMessageBlock, { kind: "activity" }>[] = [];
  let textRun = "";

  const flushActivityRun = () => {
    if (activityRun.length === 0) return;
    rows.push(<ActivitySummary blocks={activityRun} key={`${groupId}:activity:${rows.length}`} />);
    activityRun = [];
  };

  const flushTextRun = () => {
    if (!textRun) return;
    rows.push(<TimelineTextRow text={textRun} tone="text" key={`${groupId}:text:${rows.length}`} />);
    textRun = "";
  };

  blocks.forEach((block, index) => {
    if (block.kind === "activity") {
      flushTextRun();
      activityRun.push(block);
      return;
    }
    if (block.kind === "text") {
      flushActivityRun();
      textRun += block.text;
      return;
    }

    flushTextRun();
    flushActivityRun();
    rows.push(<StreamBlockRow key={`${groupId}:${index}`} block={block} onOpenDocument={onOpenDocument} />);
  });
  flushTextRun();
  flushActivityRun();

  return <>{rows}</>;
}

function StreamMessageGroupCard({
  group,
  onOpenDocument,
}: {
  group: ThreadMessageGroup;
  onOpenDocument: (document: StreamDocument) => void;
}) {
  if (group.role === "user") {
    const text = group.blocks
      .filter((block): block is Extract<StreamMessageBlock, { kind: "text" }> => block.kind === "text")
      .map((block) => block.text)
      .join("\n");
    const attachments = group.blocks.filter((block): block is Extract<StreamMessageBlock, { kind: "attachment" }> => block.kind === "attachment");

    return (
      <article className="thread-message user">
        <div className="message-bubble">
          <div className="message-meta">
            <strong>나</strong>
            <span>메시지</span>
          </div>
          {text ? <p>{text}</p> : null}
          {attachments.length > 0 ? (
            <div className="message-attachments" aria-label="첨부 파일">
              {attachments.map((attachment) => (
                <span className="message-attachment-chip" key={attachment.fileName}>
                  <Paperclip size={14} strokeWidth={1.9} />
                  <span>{attachment.fileName}</span>
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </article>
    );
  }

  return (
    <article className="thread-message assistant-flow-message">
      <div className="message-avatar">{group.role === "system" ? "!" : "LP"}</div>
      <div className="assistant-flow">
        <div className="assistant-flow-label">{group.role === "system" ? "시스템" : "LaunchPilot"}</div>
        <div className="assistant-timeline">
          <StreamBlockSequence groupId={group.id} blocks={group.blocks} onOpenDocument={onOpenDocument} />
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
    case "attachment":
      return <TimelineTextRow text={block.fileName} tone="done" />;
    case "activity":
      return <TimelineTextRow text={block.title} tone={block.status === "failed" ? "failed" : block.status === "done" ? "done" : "active"} />;
    case "markdown_document":
      return (
        <button className="timeline-chain-row document done" type="button" onClick={() => onOpenDocument(block.document)} aria-label={`${block.title} 열기`}>
          <span className="timeline-glyph" aria-hidden="true" />
          <span className="timeline-document-card">
            <FileText size={15} strokeWidth={1.8} />
            <span>{block.title} 준비 완료</span>
          </span>
        </button>
      );
    case "artifact":
      return <ArtifactTimelineRow block={block} />;
    case "approval":
      return <TimelineTextRow text={block.title} tone="active" />;
    case "result":
      return <TimelineTextRow text={block.detail ? `${block.title}. ${block.detail}` : block.title} tone="done" />;
    case "error":
      return <TimelineTextRow text={block.detail ? `${block.title}: ${block.detail}` : block.title} tone="failed" />;
  }
}

function artifactKindLabel(kind: Extract<StreamMessageBlock, { kind: "artifact" }>["artifactKind"]) {
  switch (kind) {
    case "signal":
      return "신호 아티팩트";
    case "hypothesis":
      return "가설 아티팩트";
    case "experiment_plan":
      return "실험 계획";
    case "growth_brief":
      return "그로스 브리프";
    default:
      return "아티팩트";
  }
}

function ArtifactTimelineRow({ block }: { block: Extract<StreamMessageBlock, { kind: "artifact" }> }) {
  return (
    <div className="timeline-chain-row document done">
      <span className="timeline-glyph" aria-hidden="true" />
      <span className="timeline-document-card">
        <FileText size={15} strokeWidth={1.8} />
        <span>
          <strong>{block.title}</strong>
          <small>{artifactKindLabel(block.artifactKind)}</small>
        </span>
      </span>
    </div>
  );
}

function ThreadDisplayItemRow({
  item,
  view,
  onOpenDocument,
}: {
  item: ThreadDisplayItem;
  view: ExperimentPlannerView;
  onOpenDocument: (document: StreamDocument) => void;
}) {
  if (item.kind === "decision_gate") {
    return (
      <section className="thread-gate-inline" aria-label="현재 결정">
        <GateCard gate={item.gate} view={view} canApprove={view.approval.canApprove} current />
      </section>
    );
  }

  return <StreamMessageGroupCard group={item.group} onOpenDocument={onOpenDocument} />;
}

function SystemStatusRows({ statuses }: { statuses: StatusRow[] }) {
  if (statuses.length === 0) return null;

  return (
    <div className="system-status-list" aria-label="시스템 진행 상황">
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
      <div className="topbar-context" aria-label="현재 워크스페이스">
        <span>{campaignName}</span>
      </div>
      {progress.visible ? <AgentSessionProgress progress={progress} /> : null}
      <div className="account-tools">
        <button className="round-button" aria-label="알림">
          <Bell size={17} strokeWidth={1.8} />
        </button>
        {progress.threadLabel ? (
          <button className="credit-pill" type="button">
            <span>스레드</span>
            <b>{progress.threadLabel}</b>
          </button>
        ) : null}
        <button className="avatar" aria-label="프로필">S</button>
        {canToggleInspector ? (
          <button
            className={`round-button view-toggle${inspectorOpen ? " active" : ""}`}
            type="button"
            aria-label={inspectorOpen ? "상세 패널 숨기기" : "상세 패널 열기"}
            aria-pressed={inspectorOpen}
            title={inspectorOpen ? "상세 숨기기" : "상세 보기"}
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
    <section className="agent-session-progress" aria-label="에이전트 세션 상태">
      <div className="agent-run-summary">
        <div>
          <strong>{currentStep?.label ?? "에이전트 세션"}</strong>
          <span>{progress.stateLabel}</span>
        </div>
        <span className="run-progress-count">
          {Math.min(completedCount + (activeIndex >= 0 ? 1 : 0), steps.length)} / {steps.length}
        </span>
      </div>
      <div className="run-step-strip" aria-label="에이전트 진행 단계">
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
          <b>{formatMetricValue(signal.metric_name, signal.current_value)}</b>
          현재
        </span>
        <span>
          <b>{formatMetricValue(signal.metric_name, signal.baseline_value)}</b>
          베이스라인
        </span>
        <span>
          <b>근거 {signal.evidence_refs.length}건</b>
          확보됨
        </span>
      </div>
    </article>
  );
}

function HypothesisCard({ hypothesis }: { hypothesis: Hypothesis }) {
  return (
    <article className="hypothesis-card">
      <div className="section-title compact">
        <span>가설</span>
        <small>신호와 근거 레퍼런스 기반 생성</small>
      </div>
      <blockquote>{hypothesis.statement}</blockquote>
      <p>{hypothesis.rationale}</p>
      <ul>
        <li>근거: {hypothesis.supporting_evidence_refs.join(", ")}</li>
        {hypothesis.caveats.map((caveat) => (
          <li key={caveat}>주의: {caveat}</li>
        ))}
      </ul>
    </article>
  );
}

function ExperimentEditor({
  experiment,
  selected,
  onToggle,
  onEdit,
}: {
  experiment: ExperimentItem;
  selected: boolean;
  onToggle: (experimentId: string) => void;
  onEdit: (experimentId: string, title: string) => void;
}) {
  return (
    <article className={`experiment-card${selected ? " selected" : " excluded"}`}>
      <div className="card-topline">
        <label className="experiment-include">
          <input type="checkbox" checked={selected} onChange={() => onToggle(experiment.id)} aria-label={`실험 포함: ${experiment.title}`} />
          <span>{selected ? "포함" : "제외"}</span>
        </label>
        <span className={`channel ${experiment.channel}`}>{experiment.channel}</span>
        <span>{experiment.scheduled_at}</span>
      </div>
      <h3>{experiment.title}</h3>
      <label htmlFor="experiment-title">실험 제목</label>
      <input id="experiment-title" type="text" value={experiment.title} onChange={(event) => onEdit(experiment.id, event.target.value)} />
      <dl>
        <div>
          <dt>훅</dt>
          <dd>{experiment.hook}</dd>
        </div>
        <div>
          <dt>CTA</dt>
          <dd>{experiment.cta}</dd>
        </div>
        <div>
          <dt>성공 기준</dt>
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
  const threadScrollRef = useRef<HTMLDivElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const csvInputRef = useRef<HTMLInputElement | null>(null);
  const scrollKey = useMemo(
    () =>
      [
        view.thread.groups
          .map((group) =>
            [
              group.id,
              group.blocks.length,
              group.blocks
                .map((block) => {
                  if (block.kind === "text") return `text:${block.text.length}:${block.text.slice(-80)}`;
                  if (block.kind === "activity") return `activity:${block.title}:${block.status}:${block.detail ?? ""}`;
                  if (block.kind === "artifact") return `artifact:${block.id}:${block.title}`;
                  if (block.kind === "markdown_document") return `doc:${block.id}:${block.title}`;
                  if (block.kind === "approval") return `approval:${block.id}:${block.title}`;
                  if (block.kind === "result") return `result:${block.title}:${block.detail ?? ""}`;
                  if (block.kind === "error") return `error:${block.title}:${block.detail ?? ""}`;
                  return block.kind;
                })
                .join("|"),
            ].join("~")
          )
          .join("::"),
        view.screen.statusRows.map((status) => `${status.title}:${status.detail}`).join("|"),
        view.screen.errorMessage ?? "",
        view.thread.primaryExperiment?.id ?? "",
        view.approval.receipt?.growth_brief_id ?? "",
      ].join(":"),
    [
      view.thread.groups,
      view.screen.statusRows,
      view.screen.errorMessage,
      view.thread.primaryExperiment?.id,
      view.approval.receipt?.growth_brief_id,
    ]
  );

  useLayoutEffect(() => {
    const scrollToBottom = () => {
      const scrollContainer = threadScrollRef.current;
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
      threadEndRef.current?.scrollIntoView({ block: "end", behavior: "auto" });
    };

    scrollToBottom();
    const firstFrame = window.requestAnimationFrame(() => {
      scrollToBottom();
      window.requestAnimationFrame(scrollToBottom);
    });
    return () => window.cancelAnimationFrame(firstFrame);
  }, [scrollKey]);

  useEffect(() => {
    const input = composerInputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 112)}px`;
    input.style.overflowY = input.scrollHeight > 112 ? "auto" : "hidden";
  }, [view.composer.value]);

  const handleComposerPrimaryAction = () => {
    switch (view.composer.primaryAction.kind) {
      case "analyze":
      case "retry":
        void view.commands.analyze();
        return;
      case "send":
        void view.commands.sendMessage();
        return;
      case "stop":
        void view.commands.cancel();
        return;
      case "new_session":
      case "none":
        return;
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    if (view.composer.primaryAction.kind === "none" || view.composer.primaryAction.disabled) return;
    event.preventDefault();
    handleComposerPrimaryAction();
  };

  const handleCsvAttachClick = () => {
    if (!view.composer.canAttachCsv) return;
    if (csvInputRef.current) {
      csvInputRef.current.value = "";
    }
    csvInputRef.current?.click();
  };

  return (
    <section className={`thread-panel${view.thread.hasActivity ? "" : " empty-thread"}`} aria-label="캠페인 에이전트 스레드" tabIndex={-1}>
      <div className="thread-scroll" ref={threadScrollRef}>
        {view.screen.intro ? (
          <div className="thread-empty-intro" aria-label="LaunchPilot 안내">
            <h1>{view.screen.intro.title}</h1>
            <p>{view.screen.intro.description}</p>
          </div>
        ) : null}

        <SystemStatusRows statuses={view.screen.statusRows} />

        {view.thread.items.map((item) => (
          <ThreadDisplayItemRow key={item.id} item={item} view={view} onOpenDocument={onOpenDocument} />
        ))}
        <div className="thread-scroll-anchor" ref={threadEndRef} aria-hidden="true" />
      </div>

      <div className="thread-composer">
        <input ref={csvInputRef} id="csv-input" type="file" accept=".csv,text/csv" aria-label="CSV 파일" disabled={!view.composer.canAttachCsv} onChange={onFileChange} />
        <textarea
          ref={composerInputRef}
          id="agent-question"
          className="composer-input"
          aria-label="메시지"
          value={view.composer.value}
          placeholder={view.composer.placeholder}
          rows={1}
          disabled={view.composer.inputDisabled}
          onChange={(event) => view.commands.updateQuestion(event.target.value)}
          onKeyDown={handleComposerKeyDown}
        />
        <div className="composer-toolbar">
          <button
            type="button"
            className={`composer-attach${view.composer.fileName ? "" : " empty"}${view.composer.canAttachCsv ? "" : " disabled"}`}
            disabled={!view.composer.canAttachCsv}
            onClick={handleCsvAttachClick}
            title={view.composer.fileName ? "CSV 교체" : "CSV 첨부"}
            aria-label={view.composer.fileName ? "캠페인 지표 CSV 교체" : "캠페인 지표 CSV 첨부"}
          >
            <Paperclip size={18} strokeWidth={1.8} />
            {view.composer.fileName ? null : <span>캠페인 지표 CSV 첨부</span>}
          </button>
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

  return <span>{gate.experiment ? gate.experiment.title : "실험 계획"}</span>;
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
            <dt>지표</dt>
            <dd>{gate.signal.metric_name}</dd>
          </div>
          <div>
            <dt>현재</dt>
            <dd>{formatMetricValue(gate.signal.metric_name, gate.signal.current_value)}</dd>
          </div>
          <div>
            <dt>베이스라인</dt>
            <dd>{formatMetricValue(gate.signal.metric_name, gate.signal.baseline_value)}</dd>
          </div>
          <div>
            <dt>상승률</dt>
            <dd>{gate.signal.lift_ratio.toFixed(1)}x</dd>
          </div>
        </dl>
        {gate.status === "active" ? (
          <div className="gate-actions">
            <button className="approve-button" type="button" onClick={view.commands.continueSignalReview}>
              {gate.actionLabel}
            </button>
            <button className="secondary-button" type="button" onClick={view.commands.deferSignalReview}>
              나중에 — 채팅으로 더 살펴보기
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  const selectedHypothesisId = gate.selectedHypothesisId;
  return (
    <div className="gate-body">
      {gate.hypotheses.length > 1 ? (
        <div className="hypothesis-selector" role="group" aria-label="집중할 가설 선택">
          <span className="hypothesis-selector-label">집중할 가설 선택 (해당 실험만 승인)</span>
          <div className="hypothesis-chips">
            {gate.hypotheses.map((hypothesis, index) => (
              <button
                key={hypothesis.id}
                type="button"
                className={`hypothesis-chip${selectedHypothesisId === hypothesis.id ? " selected" : ""}`}
                title={hypothesis.statement}
                onClick={() => view.commands.selectHypothesis(hypothesis.id)}
              >
                H{index + 1}: {hypothesis.statement}
              </button>
            ))}
            {selectedHypothesisId ? (
              <button
                type="button"
                className="hypothesis-chip clear"
                onClick={() => view.commands.selectHypothesis(selectedHypothesisId)}
              >
                전체 보기
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {gate.hypothesis ? <HypothesisCard hypothesis={gate.hypothesis} /> : null}
      {gate.experiment ? (
        <ExperimentEditor
          experiment={gate.experiment}
          selected={view.approval.selectedExperimentIds.includes(gate.experiment.id)}
          onToggle={view.commands.toggleExperiment}
          onEdit={view.commands.editExperiment}
        />
      ) : null}
      {view.approval.draftExperiments.slice(1).map((experiment) => {
        const selected = view.approval.selectedExperimentIds.includes(experiment.id);
        return (
          <article className={`experiment-card${selected ? "" : " excluded"}`} key={experiment.id}>
            <div className="card-topline">
              <label className="experiment-include">
                <input type="checkbox" checked={selected} onChange={() => view.commands.toggleExperiment(experiment.id)} aria-label={`실험 포함: ${experiment.title}`} />
                <span>{selected ? "포함" : "제외"}</span>
              </label>
              <span className={`channel ${experiment.channel}`}>{experiment.channel}</span>
              <span>{experiment.scheduled_at}</span>
            </div>
            <h3>{experiment.title}</h3>
            <p>{experiment.production_brief}</p>
          </article>
        );
      })}
      {view.approval.receipt ? (
        <div className="approval-receipt" tabIndex={-1}>
          <strong>승인 처리 완료</strong>
          <span>
            승인됨: {view.approval.finalExperiments[0]?.title ?? "실험 계획"}. 그로스 브리프 {view.approval.receipt.growth_brief_id}와 캘린더 이벤트{" "}
            {view.approval.calendarEvents.length}건이 생성되었습니다.
          </span>
        </div>
      ) : null}
      {gate.status === "active" ? (
        <button className={`approve-button${view.shell.campaignStatus === "approved" ? " approved" : ""}`} type="button" disabled={!canApprove} onClick={view.commands.approve}>
          {view.approval.isApproving
            ? "승인 중"
            : view.approval.selectedExperimentIds.length === 0
              ? "실험을 1개 이상 선택하세요"
              : `${gate.actionLabel} (${view.approval.selectedExperimentIds.length})`}
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
        <small>{gate.status === "active" ? "현재 게이트" : "완료"}</small>
      </summary>
      <GateContent gate={gate} view={view} canApprove={canApprove} />
    </details>
  );
}

function InspectorPanel({
  open,
  outputs,
  activeOutputId,
  openOutputIds,
  onSelectOutput,
  onCloseOutput,
}: {
  open: boolean;
  outputs: OutputPanelItem[];
  activeOutputId: string | null;
  openOutputIds: string[];
  onSelectOutput: (id: string) => void;
  onCloseOutput: (id: string) => void;
}) {
  const openOutputs = openOutputIds.map((id) => outputs.find((output) => output.id === id)).filter((output): output is OutputPanelItem => Boolean(output));
  const activeOutput = openOutputs.find((output) => output.id === activeOutputId) ?? openOutputs.at(-1) ?? null;

  return (
    <aside className="inspector-panel output-panel" aria-label="산출물 패널" aria-hidden={!open} tabIndex={open ? -1 : undefined}>
      <div className="inspector-top">
        <div>
          <strong>산출물</strong>
          <span>{outputs.length > 0 ? `저장된 산출물 ${outputs.length}건` : "아직 산출물 없음"}</span>
        </div>
      </div>

      <div className="inspector-content">
        {outputs.length > 0 ? (
          <>
            <section className="output-library" aria-label="저장된 산출물">
              <div className="output-library-heading">
                <strong>저장됨</strong>
                <span>{outputs.length}</span>
              </div>
              {outputs.map((output) => (
                <button
                  className={`output-list-card${output.id === activeOutput?.id ? " active" : ""}`}
                  type="button"
                  aria-pressed={output.id === activeOutput?.id}
                  aria-label={`${output.eyebrow} ${output.title}`}
                  key={output.id}
                  onClick={() => onSelectOutput(output.id)}
                >
                  <span className={`output-kind-dot ${output.kind}`} aria-hidden="true" />
                  <span className="output-list-copy">
                    <strong>{output.title}</strong>
                    <small>{output.summary}</small>
                  </span>
                  <span className="output-list-eyebrow">{output.eyebrow}</span>
                </button>
              ))}
            </section>

            <nav className="output-browser-tabs" aria-label="열린 산출물 탭">
              {openOutputs.map((output) => (
                <div className={`output-browser-tab${output.id === activeOutput?.id ? " active" : ""}`} key={output.id}>
                  <button type="button" onClick={() => onSelectOutput(output.id)} aria-pressed={output.id === activeOutput?.id}>
                    <span>{output.title}</span>
                  </button>
                  <button className="output-tab-close" type="button" aria-label={`${output.title} 닫기`} onClick={() => onCloseOutput(output.id)}>
                    <X size={13} strokeWidth={2} />
                  </button>
                </div>
              ))}
            </nav>

            <section className="inspector-section document-viewer" aria-label={activeOutput?.title ?? "선택된 산출물"}>
              <article className="markdown-document">
                <MarkdownContent markdown={activeOutput?.markdown ?? ""} />
              </article>
            </section>
          </>
        ) : (
          <article className="markdown-empty">
            <p>아직 저장된 산출물이 없어요.</p>
          </article>
        )}
      </div>
    </aside>
  );
}

function MarkdownContent({ markdown }: { markdown: string }) {
  const lines = normalizeAssistantMarkdown(markdown).split("\n");
  const elements: ReactNode[] = [];
  let unorderedItems: ReactNode[] = [];
  let orderedItems: ReactNode[] = [];

  const flushUnorderedList = () => {
    if (unorderedItems.length === 0) return;
    elements.push(
      <ul key={`list-${elements.length}`}>
        {unorderedItems}
      </ul>
    );
    unorderedItems = [];
  };

  const flushOrderedList = () => {
    if (orderedItems.length === 0) return;
    elements.push(
      <ol key={`ordered-list-${elements.length}`}>
        {orderedItems}
      </ol>
    );
    orderedItems = [];
  };

  const flushLists = () => {
    flushUnorderedList();
    flushOrderedList();
  };

  lines.forEach((line, index) => {
    if (line.startsWith("### ")) {
      flushLists();
      elements.push(<h3 key={index}>{parseInlineMarkdown(line.slice(4))}</h3>);
      return;
    }
    if (line.startsWith("## ")) {
      flushLists();
      elements.push(<h2 key={index}>{parseInlineMarkdown(line.slice(3))}</h2>);
      return;
    }
    if (line.startsWith("# ")) {
      flushLists();
      elements.push(<h1 key={index}>{parseInlineMarkdown(line.slice(2))}</h1>);
      return;
    }
    if (line.trim() === "---") {
      flushLists();
      elements.push(<hr key={index} />);
      return;
    }
    if (line.startsWith("- ")) {
      flushOrderedList();
      unorderedItems.push(<li key={`u-${index}`}>{parseInlineMarkdown(line.slice(2))}</li>);
      return;
    }
    const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      flushUnorderedList();
      orderedItems.push(<li key={`o-${index}`}>{parseInlineMarkdown(orderedMatch[1])}</li>);
      return;
    }
    if (!line.trim()) {
      flushLists();
      return;
    }
    flushLists();
    elements.push(<p key={index}>{parseInlineMarkdown(line)}</p>);
  });
  flushLists();

  return elements;
}

function normalizeAssistantMarkdown(markdown: string) {
  return markdown
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s+(---)(?=\s|$)/g, "$1\n\n$2")
    .replace(/([^\n])\s+(#{1,3}\s+)/g, "$1\n\n$2")
    .replace(/([^\n])\s+(\d+\.\s+\*\*)/g, "$1\n\n$2")
    .replace(/([^\n])\s+(-\s+\*\*)/g, "$1\n\n$2");
}

function parseInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text))) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }
    const token = match[0];
    const key = `${token}-${match.index}`;
    if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
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
    <section className="campaign-agent-workspace" aria-label="캠페인 에이전트 워크스페이스">
      <ThreadPanel view={view} onFileChange={onFileChange} onOpenDocument={onOpenDocument} />
    </section>
  );
}

export function ExperimentPlannerPage() {
  const router = useRouter();
  const view = useExperimentPlannerController();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [activeOutputId, setActiveOutputId] = useState<string | null>(null);
  const [openOutputIds, setOpenOutputIds] = useState<string[]>([]);
  const previousOutputCountRef = useRef(0);
  const campaignStatus = view.shell.campaignStatus === "approved" ? "승인됨" : view.shell.campaignStatus === "needs_review" ? "승인 필요" : view.shell.campaignStatus === "error" ? "주의 필요" : "진행 중";
  const canToggleInspector = true;

  useEffect(() => {
    const latestOutput = view.inspector.outputs.at(-1) ?? null;
    const activeOutputExists = activeOutputId ? view.inspector.outputs.some((output) => output.id === activeOutputId) : false;
    const outputWasAdded = view.inspector.outputs.length > previousOutputCountRef.current;
    previousOutputCountRef.current = view.inspector.outputs.length;
    if (latestOutput && (outputWasAdded || !activeOutputId || !activeOutputExists)) {
      setActiveOutputId(latestOutput.id);
      setOpenOutputIds((ids) => (ids.includes(latestOutput.id) ? ids : [...ids, latestOutput.id]));
      if (outputWasAdded && (latestOutput.id.startsWith("document:") || latestOutput.id.startsWith("signal:") || latestOutput.id.startsWith("analysis:"))) {
        setInspectorOpen(true);
      }
    }
  }, [activeOutputId, view.inspector.outputs]);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) view.commands.selectCsv(file);
  }

  function handleOpenDocument(streamDocument: StreamDocument) {
    const id = `document:${streamDocument.document_id}`;
    setActiveOutputId(id);
    setOpenOutputIds((ids) => (ids.includes(id) ? ids : [...ids, id]));
    setInspectorOpen(true);
    window.setTimeout(() => focusWorkspace(".document-viewer"), 0);
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
      <aside className="sidebar-shell" aria-label="LaunchPilot 내비게이션">
        <header className="sidebar-top">
          <div className="brand">
            <span className="brand-mark">LP</span>
            <span className="brand-word">LaunchPilot</span>
          </div>
          <div className="top-actions">
            <button
              className="icon-button"
              aria-label="사이드바 토글"
              aria-pressed={sidebarCollapsed}
              title={sidebarCollapsed ? "사이드바 펼치기" : "사이드바 접기"}
              onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={18} strokeWidth={1.8} /> : <PanelLeftClose size={18} strokeWidth={1.8} />}
            </button>
          </div>
        </header>

        <nav className="nav-list" aria-label="워크스페이스 내비게이션">
          <button className="nav-item parent" type="button" onClick={() => router.push("/")}>
            <FolderOpen size={18} strokeWidth={1.8} />
            <span>캠페인</span>
          </button>

          <section className="project-section" aria-label="현재 캠페인">
            <button className="campaign-card" type="button" onClick={() => focusWorkspace(".thread-panel")}>
              <div className="side-icon">
                <Target size={18} strokeWidth={1.8} />
              </div>
              <div className="side-row-label">
                <strong>{view.shell.campaignName}</strong>
                <small>{campaignStatus}</small>
              </div>
            </button>
            <div className="campaign-subnav" aria-label="캠페인 하위 메뉴">
              <button className="nav-item child active" type="button" onClick={() => focusWorkspace(".thread-panel")}>
                <FlaskConical size={18} strokeWidth={1.8} />
                <span>실험 플래너</span>
              </button>
              <button className="nav-item child" type="button" data-locked={!view.approval.receipt} title={view.approval.receipt ? "생성된 캘린더 이벤트 보기" : "실험을 승인하면 캘린더 이벤트가 생성됩니다"} onClick={handleOutputClick}>
                <CalendarDays size={18} strokeWidth={1.8} />
                <span>캘린더</span>
              </button>
              <button className="nav-item child" type="button" data-locked={!view.approval.receipt} title={view.approval.receipt ? "생성된 그로스 브리프 보기" : "실험을 승인하면 그로스 브리프가 생성됩니다"} onClick={handleOutputClick}>
                <FileText size={18} strokeWidth={1.8} />
                <span>브리프</span>
              </button>
            </div>
          </section>
        </nav>

        <div className="sidebar-spacer" />

        <footer className="sidebar-footer">
          <button className="icon-button" aria-label="캠페인 목록으로" title="캠페인 목록으로" onClick={() => router.push("/")}>
            <House size={18} strokeWidth={1.8} />
          </button>
          <button className="icon-button reset-button" aria-label="데모 초기화" title="데모 초기화" onClick={view.commands.reset}>
            <RotateCcw size={18} strokeWidth={1.8} />
            <span>데모 초기화</span>
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
          open={inspectorOpen}
          outputs={view.inspector.outputs}
          activeOutputId={activeOutputId}
          openOutputIds={openOutputIds}
          onSelectOutput={(id) => {
            setActiveOutputId(id);
            setOpenOutputIds((ids) => (ids.includes(id) ? ids : [...ids, id]));
            setInspectorOpen(true);
          }}
          onCloseOutput={(id) => {
            setOpenOutputIds((ids) => ids.filter((openId) => openId !== id));
            if (activeOutputId === id) {
              const remaining = openOutputIds.filter((openId) => openId !== id);
              setActiveOutputId(remaining.at(-1) ?? view.inspector.outputs.at(-1)?.id ?? null);
            }
          }}
        />
      </main>
    </div>
  );
}
