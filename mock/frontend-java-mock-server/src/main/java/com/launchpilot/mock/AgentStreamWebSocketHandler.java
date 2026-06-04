package com.launchpilot.mock;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
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
    private final Map<String, SessionState> sessions = new ConcurrentHashMap<>();

    public AgentStreamWebSocketHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        String threadId = threadIdFromSession(session);
        SessionState state = new SessionState(threadId);
        sessions.put(session.getId(), state);

        if (MockPayloads.RUN_ID.equals(threadId)) {
            state.sequence.set(11);
            new Thread(() -> replay(session, state, 1, 11)).start();
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        Map<?, ?> command = objectMapper.readValue(message.getPayload(), Map.class);
        if (!"message.send".equals(command.get("type"))) {
            return;
        }

        SessionState state = sessions.computeIfAbsent(session.getId(), ignored -> new SessionState(threadIdFromSession(session)));
        Object content = command.get("content");
        Object action = command.get("action");
        String text = content instanceof String value ? value.trim() : "";

        if (action instanceof Map<?, ?> actionMap) {
            String actionName = String.valueOf(actionMap.get("name"));
            if ("approve".equals(actionName)) {
                send(session, approvalCommitted(state));
                return;
            }
            if ("revise_artifact".equals(actionName)) {
                return;
            }
            if ("cancel".equals(actionName)) {
                send(session, assistantText(state, "User cancelled the agent session. The streamed timeline remains available for review."));
                return;
            }
            if ("reject".equals(actionName)) {
                send(session, assistantText(state, "알겠습니다. 이 안은 승인하지 않고 대화 맥락만 남겨둘게요. 다른 방향으로 다시 좁혀볼 수 있습니다."));
                return;
            }
        }

        Intent intent = classify(text);
        switch (intent) {
            case APPROVE -> send(session, approvalCommitted(state));
            case REJECT -> send(session, assistantText(state, "승인은 보류했습니다. 어떤 기준을 바꾸면 좋을지 알려주면 수정안을 다시 만들겠습니다."));
            case REQUEST_CHANGES -> sendRevisionApproval(session, state);
            case USE_SIGNAL -> {
                int fromSequence = Math.max(state.sequence.get() + 1, 12);
                state.sequence.set(16);
                new Thread(() -> replay(session, state, fromSequence, 16)).start();
            }
            case SHOW_DOCUMENT -> send(session, evidenceDocument(state));
            case ANALYZE -> new Thread(() -> replay(session, state, 2, 11)).start();
            case DUPLICATE -> sendDuplicateSignal(session, state);
            case ERROR -> send(session, errorMessage(state));
            case FREE_CHAT -> send(session, assistantText(state, deterministicOrRandomReply(text)));
        }
    }

    private Intent classify(String text) {
        String normalized = text.toLowerCase();
        if (normalized.contains("duplicate") || text.contains("중복")) return Intent.DUPLICATE;
        if (normalized.contains("error") || text.contains("에러")) return Intent.ERROR;
        if (normalized.contains("approve") || text.contains("승인") || text.contains("좋아 진행")) return Intent.APPROVE;
        if (normalized.contains("reject") || text.contains("거절") || text.contains("보류")) return Intent.REJECT;
        if (normalized.contains("remove") || normalized.contains("revise") || text.contains("빼") || text.contains("수정")) return Intent.REQUEST_CHANGES;
        if (normalized.contains("use this signal") || text.contains("시그널 사용할") || text.contains("signal 사용할")) return Intent.USE_SIGNAL;
        if (normalized.contains("document") || normalized.contains("evidence") || text.contains("문서") || text.contains("근거")) return Intent.SHOW_DOCUMENT;
        if (normalized.contains("analyze") || normalized.contains("analysis") || text.contains("분석") || text.contains("이상한 점") || text.contains("찾아줘")) return Intent.ANALYZE;
        return Intent.FREE_CHAT;
    }

    private String deterministicOrRandomReply(String text) {
        String normalized = text.toLowerCase();
        if (normalized.contains("what") || text.contains("뭐부터") || text.contains("무엇부터")) {
            return "우선 저장률과 댓글 전환처럼 다음 실행으로 이어지는 지표부터 보겠습니다. 데이터가 들어오면 제가 근거 문서와 실험 후보를 함께 올릴게요.";
        }
        if (normalized.contains("retention") || text.contains("리텐션")) {
            return "좋아요. 리텐션 관점이면 단순 조회수보다 저장률, 재방문을 유도한 CTA, 댓글의 후속 행동 신호를 우선 보겠습니다.";
        }
        return randomConversationReply();
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

    private void replay(WebSocketSession session, SessionState state, int fromSequence, int toSequence) {
        for (Map<String, Object> event : events(state.threadId)) {
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

    private List<Map<String, Object>> events(String threadId) {
        return List.of(
                streamMessage(threadId, 1, "user", List.of(Map.of("kind", "text", "text", "What should we test next week?"))),
                streamMessage(threadId, 2, "assistant", List.of(Map.of("kind", "activity", "id", "act_import_metrics", "title", "Imported campaign metrics", "status", "done"))),
                streamMessage(threadId, 3, "assistant", List.of(Map.of("kind", "text", "text", "I am comparing the uploaded campaign metrics against the recent baseline and preparing an evidence document."))),
                streamMessage(threadId, 4, "assistant", List.of(Map.of("kind", "activity", "id", "query_metric_baseline", "title", "Checking metric baseline", "status", "running"))),
                streamMessage(threadId, 5, "assistant", List.of(Map.of("kind", "activity", "id", "query_metric_baseline", "title", "Checked metric baseline", "status", "done", "detail", "Completed in 412ms."))),
                streamMessage(threadId, 6, "assistant", List.of(Map.of("kind", "text", "text", "The save-rate lift looks repeatable, so I am checking whether content evidence supports it."))),
                streamMessage(threadId, 7, "assistant", List.of(Map.of("kind", "activity", "id", "search_content_posts", "title", "Searching supporting posts", "status", "running"))),
                streamMessage(threadId, 8, "assistant", List.of(Map.of("kind", "activity", "id", "search_content_posts", "title", "Checked supporting posts", "status", "done", "detail", "Completed in 586ms."))),
                streamMessage(threadId, 9, "assistant", List.of(
                        Map.of("kind", "text", "text", "The agent found two BTS shorts that outperformed the recent baseline."),
                        Map.of("kind", "artifact", "id", "artifact_signal_payload", "artifact_kind", "signal", "title", "BTS shorts outperformed recent baseline", "content", MockPayloads.payload())
                )),
                evidenceDocument(threadId, 10),
                streamMessage(threadId, 12, "assistant", List.of(Map.of("kind", "activity", "id", "search_team_notes", "title", "Searching team notes", "status", "running"))),
                streamMessage(threadId, 13, "assistant", List.of(Map.of("kind", "activity", "id", "search_team_notes", "title", "Checked team notes", "status", "done", "detail", "Completed in 344ms."))),
                streamMessage(threadId, 14, "assistant", List.of(
                        Map.of("kind", "text", "text", "Raw behind-the-scenes clips may be converting passive viewers into deeper engagement."),
                        Map.of("kind", "artifact", "id", "artifact_hypothesis_payload", "artifact_kind", "hypothesis", "title", "Hypothesis generated", "content", MockPayloads.payload())
                )),
                streamMessage(threadId, 15, "assistant", List.of(
                        Map.of("kind", "text", "text", "An experiment plan is ready for review."),
                        Map.of("kind", "artifact", "id", "artifact_plan_payload", "artifact_kind", "experiment_plan", "title", "Experiment plan drafted", "content", MockPayloads.payload())
                )),
                approvalRequest(threadId, 16, MockPayloads.payload())
        );
    }

    private Map<String, Object> assistantText(SessionState state, String text) {
        return streamMessage(state.threadId, state.sequence.incrementAndGet(), "assistant", List.of(Map.of("kind", "text", "text", text)));
    }

    private Map<String, Object> evidenceDocument(SessionState state) {
        return evidenceDocument(state.threadId, state.sequence.incrementAndGet());
    }

    private Map<String, Object> evidenceDocument(String threadId, int sequence) {
        return streamMessage(threadId, sequence, "assistant", List.of(Map.of(
                "kind", "markdown_document",
                "id", "doc_evidence_scan_001",
                "title", "Evidence notes",
                "summary", "Evidence notes for the uploaded campaign metrics.",
                "markdown", "## Evidence notes\n\nI am comparing uploaded campaign metrics against the recent baseline.\n\n- Checking lift by channel\n- Looking for repeatable content patterns\n- Preparing candidate experiments"
        )));
    }

    private Map<String, Object> approvalRequest(String threadId, int sequence, Map<String, Object> payload) {
        return streamMessage(threadId, sequence, "assistant", List.of(Map.of(
                "kind", "approval",
                "id", "appr_mock_001",
                "title", "Approve experiment plan",
                "target_id", "plan_001",
                "actions", List.of("approve", "reject", "request_changes"),
                "payload", payload
        )));
    }

    private void sendRevisionApproval(WebSocketSession session, SessionState state) throws IOException {
        send(session, streamMessage(state.threadId, state.sequence.incrementAndGet(), "assistant", List.of(Map.of("kind", "text", "text", "두 번째 실험은 제외하고 승인 가능한 초안으로 다시 정리했습니다."))));
        send(session, approvalRequest(state.threadId, state.sequence.incrementAndGet(), MockPayloads.payloadWithoutSecondExperiment()));
    }

    private void sendDuplicateSignal(WebSocketSession session, SessionState state) throws IOException {
        int sequence = state.sequence.incrementAndGet();
        Map<String, Object> signal = streamMessage(state.threadId, sequence, "assistant", List.of(
                Map.of("kind", "artifact", "id", "artifact_duplicate_signal_payload", "artifact_kind", "signal", "title", "Duplicate signal fixture", "content", MockPayloads.payload())
        ));
        send(session, signal);
        send(session, signal);
    }

    private Map<String, Object> errorMessage(SessionState state) {
        return streamMessage(state.threadId, state.sequence.incrementAndGet(), "system", List.of(Map.of(
                "kind", "error",
                "title", "Mock agent tool error",
                "detail", "The mock server generated a retryable error block for E2E coverage.",
                "retryable", true
        )));
    }

    private Map<String, Object> approvalCommitted(SessionState state) {
        return streamMessage(state.threadId, state.sequence.incrementAndGet(), "assistant", List.of(Map.of(
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

    private Map<String, Object> streamMessage(String threadId, int sequence, String role, List<Map<String, Object>> blocks) {
        Map<String, Object> message = new java.util.LinkedHashMap<>();
        message.put("id", "msg_mock_" + String.format("%03d", sequence));
        message.put("thread_id", threadId);
        message.put("sequence", sequence);
        message.put("role", role);
        message.put("created_at", OffsetDateTime.now().toString());
        message.put("blocks", blocks);
        return message;
    }

    private String threadIdFromSession(WebSocketSession session) {
        URI uri = session.getUri();
        if (uri == null) return MockPayloads.RUN_ID;
        String path = uri.getPath();
        String marker = "/api/agent/threads/";
        int start = path.indexOf(marker);
        if (start < 0) return MockPayloads.RUN_ID;
        int idStart = start + marker.length();
        int idEnd = path.indexOf("/stream", idStart);
        return idEnd > idStart ? path.substring(idStart, idEnd) : MockPayloads.RUN_ID;
    }

    private void send(WebSocketSession session, Map<String, Object> payload) throws IOException {
        if (session.isOpen()) {
            session.sendMessage(new TextMessage(toJson(payload)));
        }
    }

    private String toJson(Map<String, Object> payload) throws JsonProcessingException {
        return objectMapper.writeValueAsString(payload);
    }

    private enum Intent {
        FREE_CHAT,
        ANALYZE,
        SHOW_DOCUMENT,
        USE_SIGNAL,
        APPROVE,
        REJECT,
        REQUEST_CHANGES,
        DUPLICATE,
        ERROR
    }

    private static final class SessionState {
        final String threadId;
        final AtomicInteger sequence;

        SessionState(String threadId) {
            this.threadId = threadId;
            this.sequence = new AtomicInteger(0);
        }
    }
}
