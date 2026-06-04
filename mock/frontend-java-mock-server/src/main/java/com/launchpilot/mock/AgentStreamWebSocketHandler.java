package com.launchpilot.mock;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class AgentStreamWebSocketHandler extends TextWebSocketHandler {
    private final ObjectMapper objectMapper;
    private final Map<String, AtomicInteger> checkpoints = new ConcurrentHashMap<>();

    public AgentStreamWebSocketHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        checkpoints.put(session.getId(), new AtomicInteger(11));
        new Thread(() -> replay(session, 1, 11)).start();
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        Map<?, ?> command = objectMapper.readValue(message.getPayload(), Map.class);
        Object type = command.get("type");
        if ("connection.resume".equals(type)) {
            int last = command.get("last_received_sequence") instanceof Number number ? number.intValue() : 0;
            send(session, event(100, "connection.resume_accepted", Map.of(
                    "last_replayed_sequence", last,
                    "next_expected_sequence", last + 1
            )));
            new Thread(() -> replay(session, last + 1, checkpointFor(last))).start();
            return;
        }
        if ("connection.full_sync".equals(type)) {
            new Thread(() -> replay(session, 1, checkpoints.getOrDefault(session.getId(), new AtomicInteger(11)).get())).start();
            return;
        }
        if ("run.continue".equals(type)) {
            AtomicInteger checkpoint = checkpoints.computeIfAbsent(session.getId(), ignored -> new AtomicInteger(11));
            int fromSequence = checkpoint.get() + 1;
            checkpoint.set(16);
            new Thread(() -> replay(session, fromSequence, 16)).start();
            return;
        }
        if ("approval.approve".equals(type)) {
            send(session, approvalCommitted());
            return;
        }
        if ("approval.reject".equals(type) || "run.cancel".equals(type)) {
            Object reason = command.get("reason");
            send(session, event(18, "run.cancelled", Map.of(
                    "status", "CANCELLED",
                    "error_message", reason instanceof String value ? value : "Agent run cancelled."
            )));
        }
    }

    private static int nextCheckpoint(int current) {
        if (current < 12) return 12;
        if (current < 13) return 13;
        if (current < 14) return 14;
        if (current < 15) return 15;
        if (current < 16) return 16;
        return 16;
    }

    private static int checkpointFor(int lastReceivedSequence) {
        if (lastReceivedSequence < 11) return 11;
        if (lastReceivedSequence < 12) return 12;
        if (lastReceivedSequence < 13) return 13;
        if (lastReceivedSequence < 14) return 14;
        if (lastReceivedSequence < 15) return 15;
        return 16;
    }

    private void replay(WebSocketSession session, int fromSequence, int toSequence) {
        for (Map<String, Object> event : events()) {
            Object sequence = event.get("sequence");
            if (sequence instanceof Number number && (number.intValue() < fromSequence || number.intValue() > toSequence)) {
                continue;
            }
            try {
                Thread.sleep(650);
                send(session, event);
            } catch (InterruptedException | IOException ignored) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    private List<Map<String, Object>> events() {
        return List.of(
        event(1, "user.message.created", Map.of(
                "status", "PENDING",
                "message", Map.of("message_id", "msg_mock_user_001", "role", "user", "content", "What should we test next week?")
        )),
        event(2, "run.started", Map.of(
                "status", "RUNNING_SIGNAL_DETECTION",
                "step", step("step_import_metrics", 1, "IMPORT_METRICS", "SUCCEEDED")
        )),
        event(3, "assistant.message.created", Map.of(
                "status", "RUNNING_EVIDENCE_SEARCH",
                "message", Map.of("message_id", "msg_mock_assistant_001", "role", "assistant", "content", "I am comparing the uploaded campaign metrics against the recent baseline and preparing an evidence document.")
        )),
        event(4, "tool.updated", Map.of(
                "status", "RUNNING_EVIDENCE_SEARCH",
                "step", step("step_search_evidence", 2, "GROUND_WITH_EVIDENCE", "IN_PROGRESS"),
                "tool_call", toolCall(1, "query_metric_baseline", "RUNNING", 0)
        )),
        event(5, "tool.updated", Map.of(
                "status", "RUNNING_EVIDENCE_SEARCH",
                "step", step("step_search_evidence", 2, "GROUND_WITH_EVIDENCE", "IN_PROGRESS"),
                "tool_call", toolCall(1, "query_metric_baseline", "SUCCESS", 412)
        )),
        event(6, "observation.created", Map.of(
                "status", "RUNNING_EVIDENCE_SEARCH",
                "step", step("step_search_evidence", 2, "GROUND_WITH_EVIDENCE", "IN_PROGRESS"),
                "observation", Map.of(
                        "id", "obs_reasoning_metric_first",
                        "kind", "progress",
                        "title", "Reasoning update",
                        "summary", "The save-rate lift looks repeatable, so I am checking whether content evidence supports it.",
                        "evidence_refs", List.of()
                )
        )),
        event(7, "tool.updated", Map.of(
                "status", "RUNNING_EVIDENCE_SEARCH",
                "step", step("step_search_evidence", 2, "GROUND_WITH_EVIDENCE", "IN_PROGRESS"),
                "tool_call", toolCall(2, "search_content_posts", "RUNNING", 0)
        )),
        event(8, "tool.updated", Map.of(
                "status", "RUNNING_EVIDENCE_SEARCH",
                "step", step("step_search_evidence", 2, "GROUND_WITH_EVIDENCE", "IN_PROGRESS"),
                "tool_call", toolCall(2, "search_content_posts", "SUCCESS", 586)
        )),
        event(9, "signal.detected", Map.of(
                "status", "RUNNING_HYPOTHESIS_GENERATION",
                "step", step("step_search_evidence", 2, "GROUND_WITH_EVIDENCE", "SUCCEEDED"),
                "observation", Map.of(
                        "id", "obs_signal_detected",
                        "kind", "signal",
                        "title", "BTS shorts outperformed recent baseline",
                        "summary", "The agent found two BTS shorts that outperformed the recent baseline.",
                        "evidence_refs", List.of("post_014", "post_017")
                ),
                "payload", MockPayloads.payload()
        )),
        event(10, "document.created", Map.of(
                "status", "RUNNING_HYPOTHESIS_GENERATION",
                "document", Map.of(
                        "document_id", "doc_evidence_scan_001",
                        "kind", "evidence_scan",
                        "title", "Evidence notes",
                        "format", "markdown",
                        "summary", "Evidence notes for the uploaded campaign metrics.",
                        "content", "## Evidence notes\n\nI am comparing uploaded campaign metrics against the recent baseline.\n\n- Checking lift by channel\n- Looking for repeatable content patterns\n- Preparing candidate experiments"
                )
        )),
        event(12, "tool.updated", Map.of(
                "status", "RUNNING_HYPOTHESIS_GENERATION",
                "step", step("step_generate_hypotheses", 3, "GENERATE_HYPOTHESIS", "IN_PROGRESS"),
                "tool_call", toolCall(3, "search_team_notes", "RUNNING", 0)
        )),
        event(13, "tool.updated", Map.of(
                "status", "RUNNING_HYPOTHESIS_GENERATION",
                "step", step("step_generate_hypotheses", 3, "GENERATE_HYPOTHESIS", "IN_PROGRESS"),
                "tool_call", toolCall(3, "search_team_notes", "SUCCESS", 344)
        )),
        event(14, "hypothesis.created", Map.of(
                "status", "RUNNING_EXPERIMENT_GENERATION",
                "step", step("step_generate_hypotheses", 3, "GENERATE_HYPOTHESIS", "SUCCEEDED"),
                "observation", Map.of("id", "obs_hypothesis_created", "kind", "hypothesis", "title", "Hypothesis generated", "summary", "Raw behind-the-scenes clips may be converting passive viewers into deeper engagement.", "evidence_refs", List.of("post_014", "post_017")),
                "payload", MockPayloads.payload()
        )),
        event(15, "experiment_plan.drafted", Map.of(
                "status", "RUNNING_EXPERIMENT_GENERATION",
                "step", step("step_draft_plan", 4, "DRAFT_EXPERIMENT_PLAN", "SUCCEEDED"),
                "observation", Map.of("id", "obs_plan_drafted", "kind", "plan", "title", "Experiment plan drafted", "summary", "An experiment plan is ready for review.", "evidence_refs", List.of()),
                "payload", MockPayloads.payload()
        )),
        event(16, "approval.requested", Map.of(
                "status", "WAITING_FOR_APPROVAL",
                "step", step("step_review_plan", 5, "WAIT_FOR_APPROVAL", "IN_PROGRESS"),
                "approval", Map.of("approval_id", "appr_mock_001", "gate", "EXPERIMENT_PLAN", "payload", MockPayloads.payload()),
                "payload", MockPayloads.payload()
        ))
        );
    }

    private Map<String, Object> approvalCommitted() {
        return event(17, "approval.committed", Map.of(
                "status", "SUCCESS",
                "approval_result", Map.of(
                        "approval_id", "appr_mock_001",
                        "growth_brief_id", "brief_20260601_001",
                        "created_calendar_events", List.of(Map.of(
                                "event_id", "cal_20260603_001",
                                "title", "BTS face-first hook test",
                                "scheduled_at", "2026-06-03T20:00:00+09:00"
                        )),
                        "persisted_at", "2026-06-01T16:33:15+09:00"
                )
        ));
    }

    private Map<String, Object> event(int sequence, String type, Map<String, Object> extra) {
        Map<String, Object> event = new java.util.LinkedHashMap<>();
        event.put("event_id", "evt_mock_" + String.format("%03d", sequence));
        event.put("type", type);
        event.put("agent_run_id", MockPayloads.RUN_ID);
        event.put("session_id", MockPayloads.SESSION_ID);
        event.put("sequence", sequence);
        event.put("occurred_at", OffsetDateTime.now().toString());
        event.put("step", null);
        event.put("message", null);
        event.put("document", null);
        event.put("observation", null);
        event.put("tool_call", null);
        event.put("payload", null);
        event.put("approval", null);
        event.put("approval_result", null);
        event.put("error_message", null);
        event.putAll(extra);
        return event;
    }

    private Map<String, Object> step(String id, int order, String stage, String status) {
        return Map.of("id", id, "order", order, "stage", stage, "status", status);
    }

    private Map<String, Object> toolCall(int sequence, String toolName, String status, Integer durationMs) {
        return Map.of("sequence", sequence, "tool_name", toolName, "status", status, "duration_ms", durationMs);
    }

    private void send(WebSocketSession session, Map<String, Object> payload) throws IOException {
        if (session.isOpen()) {
            session.sendMessage(new TextMessage(toJson(payload)));
        }
    }

    private String toJson(Map<String, Object> payload) throws JsonProcessingException {
        return objectMapper.writeValueAsString(payload);
    }
}
