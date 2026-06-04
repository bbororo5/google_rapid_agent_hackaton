package com.launchpilot.mock;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadLocalRandom;
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
        if ("message.send".equals(type)) {
            AtomicInteger checkpoint = checkpoints.computeIfAbsent(session.getId(), ignored -> new AtomicInteger(11));
            Object content = command.get("content");
            Object action = command.get("action");
            if (action instanceof Map<?, ?> actionMap && "approve".equals(actionMap.get("name"))) {
                send(session, approvalCommitted());
                return;
            }
            if (action instanceof Map<?, ?> actionMap && ("reject".equals(actionMap.get("name")) || "cancel".equals(actionMap.get("name")))) {
                return;
            }
            if (content instanceof String value && "Use this signal".equalsIgnoreCase(value.trim())) {
                int fromSequence = checkpoint.get() + 1;
                checkpoint.set(16);
                new Thread(() -> replay(session, fromSequence, 16)).start();
                return;
            }
            int sequence = checkpoint.incrementAndGet();
            send(session, streamMessage(sequence, "assistant", List.of(Map.of("kind", "text", "text", randomConversationReply()))));
            return;
        }
    }

    private String randomConversationReply() {
        List<String> replies = List.of(
                "좋아요. 지금 대화 맥락은 캠페인 실험 설계 쪽으로 이해했어요. 필요한 근거가 생기면 제가 먼저 확인하겠습니다.",
                "그 관점 괜찮습니다. 우선 리텐션, 저장률, 댓글 전환처럼 다음 액션으로 이어지는 지표를 중심으로 보겠습니다.",
                "메모해둘게요. 지금 요청은 단순 요약보다 다음 주 실행안을 만드는 쪽에 더 가깝습니다.",
                "좋은 방향이에요. 데이터가 충분하면 근거를 붙이고, 부족하면 어떤 데이터가 필요한지 먼저 짚겠습니다.",
                "이건 바로 실험안으로 밀기보다 가설을 한 번 더 좁혀보면 좋겠습니다. 사용자가 납득할 수 있는 근거를 우선하겠습니다.",
                "알겠습니다. 지금은 과한 자동화보다 사용자가 검토하고 수정할 수 있는 초안을 만드는 방식이 더 안전해 보입니다.",
                "그 요청은 캠페인 맥락과 지난 승인 브리프를 같이 보면 더 정확해집니다. 이어지는 흐름으로 정리하겠습니다.",
                "좋아요. 제가 보기엔 숫자 변화, 콘텐츠 포맷, 팀 메모를 함께 묶어야 설명 가능한 결론이 나옵니다.",
                "이 방향이면 스레드에는 짧게 요약하고, 자세한 문서는 우측 패널에 올리는 방식이 가장 읽기 좋겠습니다.",
                "확인했습니다. 필요한 경우 도구 로그와 근거 문서를 남기되, 대화 흐름은 계속 자연스럽게 유지하겠습니다."
        );
        return replies.get(ThreadLocalRandom.current().nextInt(replies.size()));
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
        streamMessage(1, "user", List.of(Map.of("kind", "text", "text", "What should we test next week?"))),
        streamMessage(2, "assistant", List.of(Map.of("kind", "activity", "id", "act_import_metrics", "title", "Imported campaign metrics", "status", "done"))),
        streamMessage(3, "assistant", List.of(Map.of("kind", "text", "text", "I am comparing the uploaded campaign metrics against the recent baseline and preparing an evidence document."))),
        streamMessage(4, "assistant", List.of(Map.of("kind", "activity", "id", "query_metric_baseline", "title", "Checking metric baseline", "status", "running"))),
        streamMessage(5, "assistant", List.of(Map.of("kind", "activity", "id", "query_metric_baseline", "title", "Checked metric baseline", "status", "done", "detail", "Completed in 412ms."))),
        streamMessage(6, "assistant", List.of(Map.of("kind", "text", "text", "The save-rate lift looks repeatable, so I am checking whether content evidence supports it."))),
        streamMessage(7, "assistant", List.of(Map.of("kind", "activity", "id", "search_content_posts", "title", "Searching supporting posts", "status", "running"))),
        streamMessage(8, "assistant", List.of(Map.of("kind", "activity", "id", "search_content_posts", "title", "Checked supporting posts", "status", "done", "detail", "Completed in 586ms."))),
        streamMessage(9, "assistant", List.of(
                Map.of("kind", "text", "text", "The agent found two BTS shorts that outperformed the recent baseline."),
                Map.of("kind", "artifact", "id", "artifact_signal_payload", "artifact_kind", "signal", "title", "BTS shorts outperformed recent baseline", "content", MockPayloads.payload())
        )),
        streamMessage(10, "assistant", List.of(Map.of(
                "kind", "markdown_document",
                "id", "doc_evidence_scan_001",
                "title", "Evidence notes",
                "summary", "Evidence notes for the uploaded campaign metrics.",
                "markdown", "## Evidence notes\n\nI am comparing uploaded campaign metrics against the recent baseline.\n\n- Checking lift by channel\n- Looking for repeatable content patterns\n- Preparing candidate experiments"
        ))),
        streamMessage(12, "assistant", List.of(Map.of("kind", "activity", "id", "search_team_notes", "title", "Searching team notes", "status", "running"))),
        streamMessage(13, "assistant", List.of(Map.of("kind", "activity", "id", "search_team_notes", "title", "Checked team notes", "status", "done", "detail", "Completed in 344ms."))),
        streamMessage(14, "assistant", List.of(
                Map.of("kind", "text", "text", "Raw behind-the-scenes clips may be converting passive viewers into deeper engagement."),
                Map.of("kind", "artifact", "id", "artifact_hypothesis_payload", "artifact_kind", "hypothesis", "title", "Hypothesis generated", "content", MockPayloads.payload())
        )),
        streamMessage(15, "assistant", List.of(
                Map.of("kind", "text", "text", "An experiment plan is ready for review."),
                Map.of("kind", "artifact", "id", "artifact_plan_payload", "artifact_kind", "experiment_plan", "title", "Experiment plan drafted", "content", MockPayloads.payload())
        )),
        streamMessage(16, "assistant", List.of(Map.of(
                "kind", "approval",
                "id", "appr_mock_001",
                "title", "Approve experiment plan",
                "target_id", "plan_001",
                "actions", List.of("approve", "reject", "request_changes"),
                "payload", MockPayloads.payload()
        )))
        );
    }

    private Map<String, Object> approvalCommitted() {
        return streamMessage(17, "assistant", List.of(Map.of(
                "kind", "result",
                "title", "Approval complete",
                "detail", "Growth brief brief_20260601_001 and 1 calendar event are ready.",
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
        )));
    }

    private Map<String, Object> streamMessage(int sequence, String role, List<Map<String, Object>> blocks) {
        Map<String, Object> message = new java.util.LinkedHashMap<>();
        message.put("id", "msg_mock_" + String.format("%03d", sequence));
        message.put("thread_id", MockPayloads.RUN_ID);
        message.put("sequence", sequence);
        message.put("role", role);
        message.put("created_at", OffsetDateTime.now().toString());
        message.put("blocks", blocks);
        return message;
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
