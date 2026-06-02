import type { AgentStreamServerEvent, AgentStepSnapshot, AgentRunStatusResponse } from "@contracts/frontend-types";
import readyFixture from "../../../../../../contracts/01-frontend-java/examples/agent-run-waiting-for-approval-response.json";
import type { AgentStreamApi, AgentStreamConnection } from "./agentStreamApi";

const readyResponse = readyFixture as AgentRunStatusResponse;

function step(id: string, order: number, status: AgentStepSnapshot["status"]): AgentStepSnapshot {
  const stageByOrder: AgentStepSnapshot["stage"][] = [
    "IMPORT_METRICS",
    "DETECT_PERFORMANCE_SIGNAL",
    "GROUND_WITH_EVIDENCE",
    "GENERATE_HYPOTHESIS",
    "DRAFT_EXPERIMENT_PLAN",
    "WAIT_FOR_APPROVAL",
  ];

  return {
    id,
    order,
    stage: stageByOrder[order - 1] ?? "GROUND_WITH_EVIDENCE",
    status,
  };
}

function event(input: Partial<AgentStreamServerEvent> & { type: AgentStreamServerEvent["type"]; agent_run_id: string; sequence: number }): AgentStreamServerEvent {
  return {
    event_id: `evt_mock_${String(input.sequence).padStart(3, "0")}`,
    occurred_at: new Date(Date.now() + input.sequence * 1000).toISOString(),
    step: null,
    observation: null,
    payload: null,
    approval: null,
    error_message: null,
    ...input,
  };
}

function buildMockEvents(agentRunId: string): AgentStreamServerEvent[] {
  const payload = readyResponse.payload;

  return [
    event({
      type: "user.message.created",
      agent_run_id: agentRunId,
      sequence: 1,
      status: "PENDING",
      message: {
        message_id: "msg_mock_user_001",
        role: "user",
        content: "What should we test next week?",
      },
    }),
    event({
      type: "run.started",
      agent_run_id: agentRunId,
      sequence: 2,
      status: "RUNNING_SIGNAL_DETECTION",
      step: step("step_import_metrics", 1, "SUCCEEDED"),
    }),
    event({
      type: "observation.created",
      agent_run_id: agentRunId,
      sequence: 3,
      status: "RUNNING_EVIDENCE_SEARCH",
      step: step("step_search_evidence", 2, "IN_PROGRESS"),
      observation: {
        id: "obs_signal_scan",
        kind: "evidence",
        title: "Performance signal scan started",
        summary: "The agent is comparing channel metrics against the recent campaign baseline.",
        evidence_refs: [],
      },
    }),
    event({
      type: "signal.detected",
      agent_run_id: agentRunId,
      sequence: 4,
      status: "RUNNING_HYPOTHESIS_GENERATION",
      step: step("step_search_evidence", 2, "SUCCEEDED"),
      observation: {
        id: "obs_signal_detected",
        kind: "signal",
        title: payload?.signals[0]?.title ?? "Campaign signal detected",
        summary: payload?.signals[0]?.description ?? "A campaign metric moved materially above baseline.",
        evidence_refs: payload?.signals[0]?.evidence_refs ?? [],
      },
      payload,
    }),
    event({
      type: "hypothesis.created",
      agent_run_id: agentRunId,
      sequence: 5,
      status: "RUNNING_EXPERIMENT_GENERATION",
      step: step("step_generate_hypotheses", 3, "SUCCEEDED"),
      observation: {
        id: "obs_hypothesis_created",
        kind: "hypothesis",
        title: "Hypothesis generated",
        summary: payload?.hypotheses[0]?.statement ?? "A hypothesis was generated from the detected signal.",
        evidence_refs: payload?.hypotheses[0]?.supporting_evidence_refs ?? [],
      },
      payload,
    }),
    event({
      type: "experiment_plan.drafted",
      agent_run_id: agentRunId,
      sequence: 6,
      status: "RUNNING_EXPERIMENT_GENERATION",
      step: step("step_draft_plan", 4, "SUCCEEDED"),
      observation: {
        id: "obs_plan_drafted",
        kind: "plan",
        title: payload?.experiment_plan.items[0]?.title ?? "Experiment plan drafted",
        summary: payload?.experiment_plan.summary ?? "An experiment plan is ready for review.",
        evidence_refs: [],
      },
      payload,
    }),
    event({
      type: "approval.requested",
      agent_run_id: agentRunId,
      sequence: 7,
      status: "WAITING_FOR_APPROVAL",
      step: step("step_review_plan", 5, "IN_PROGRESS"),
      approval: {
        approval_id: "appr_mock_001",
        gate: "EXPERIMENT_PLAN",
        payload: payload!,
      },
      payload,
    }),
  ];
}

function approvalCommittedEvent(agentRunId: string, title?: string): AgentStreamServerEvent {
  return event({
    type: "approval.committed",
    agent_run_id: agentRunId,
    sequence: 8,
    status: "SUCCESS",
    approval_result: {
      approval_id: "appr_mock_001",
      growth_brief_id: "brief_20260601_001",
      created_calendar_events: [
        {
          event_id: "cal_20260603_001",
          title: title ?? readyResponse.payload?.experiment_plan.items[0]?.title ?? "Approved experiment",
          scheduled_at: readyResponse.payload?.experiment_plan.items[0]?.scheduled_at ?? "2026-06-03T20:00:00+09:00",
        },
      ],
      persisted_at: new Date().toISOString(),
    },
  });
}

function cancelledEvent(agentRunId: string, reason: string | null | undefined): AgentStreamServerEvent {
  return event({
    type: "run.cancelled",
    agent_run_id: agentRunId,
    sequence: 9,
    status: "CANCELLED",
    error_message: reason ?? "Agent run cancelled.",
  });
}

export function createMockAgentStreamApi(): AgentStreamApi {
  return {
    connect({ agentRunId, onOpen, onEvent }) {
      let closed = false;
      let paused = false;
      let cursor = 0;
      let editedTitle: string | undefined;
      const timers: number[] = [];
      const events = buildMockEvents(agentRunId);

      const emitNext = () => {
        if (closed || paused || cursor >= events.length) return;
        const streamEvent = events[cursor];
        cursor += 1;
        onEvent(streamEvent);

        if (streamEvent.type === "signal.detected") {
          paused = true;
          return;
        }

        timers.push(window.setTimeout(emitNext, 640));
      };

      timers.push(window.setTimeout(onOpen, 60));
      timers.push(window.setTimeout(emitNext, 360));

      const connection: AgentStreamConnection = {
        send(command) {
          if (closed) return;
          if (command.type === "connection.resume") {
            return;
          }
          if (command.type === "connection.full_sync") {
            cursor = 0;
            timers.push(window.setTimeout(emitNext, 120));
            return;
          }
          if (command.type === "approval.update_payload") {
            editedTitle = command.final_experiments?.[0]?.title ?? editedTitle;
            return;
          }
          if (command.type === "approval.approve") {
            const approvedTitle = command.final_experiments?.[0]?.title ?? editedTitle;
            timers.push(window.setTimeout(() => onEvent(approvalCommittedEvent(agentRunId, approvedTitle)), 520));
            return;
          }
          if (command.type === "approval.reject" || command.type === "run.cancel") {
            timers.push(window.setTimeout(() => onEvent(cancelledEvent(agentRunId, command.reason)), 240));
          }
        },
        resume() {
          if (closed) return;
          paused = false;
          timers.push(window.setTimeout(emitNext, 360));
        },
        close() {
          closed = true;
          timers.forEach((timer) => window.clearTimeout(timer));
        },
      };

      return connection;
    },
  };
}
