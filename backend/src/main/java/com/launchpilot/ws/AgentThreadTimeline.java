package com.launchpilot.ws;

import com.launchpilot.dto.common.StreamMessage;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/**
 * 계약 01: thread별 영속(인메모리) 메시지 타임라인 + 단조 sequence.
 * 단일 인스턴스 가정 (DESIGN.md registry와 동일 전제).
 */
@Component
public class AgentThreadTimeline {

    private final Map<String, List<StreamMessage>> events = new ConcurrentHashMap<>();
    private final Map<String, AtomicLong> seq = new ConcurrentHashMap<>();

    public synchronized StreamMessage commit(String threadId, String role, List<Map<String, Object>> blocks) {
        long s = seq.computeIfAbsent(threadId, k -> new AtomicLong()).incrementAndGet();
        StreamMessage message = new StreamMessage(
                "msg_" + stripThread(threadId) + "_" + s,
                threadId,
                s,
                role,
                OffsetDateTime.now().toString(),
                blocks);
        events.computeIfAbsent(threadId, k -> new ArrayList<>()).add(message);
        return message;
    }

    private String stripThread(String threadId) {
        return threadId.startsWith("thread_") ? threadId.substring("thread_".length()) : threadId;
    }
}
