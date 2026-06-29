package com.launchpilot.conversation;

import com.launchpilot.dto.common.StreamMessage;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/**
 * Thread-local in-memory timeline with monotonic sequence numbers.
 * Single Java instance assumption matches the current MVP runtime.
 */
@Component
public class InMemoryConversationTimeline implements ConversationTimeline {

    private final Map<String, List<StreamMessage>> events = new ConcurrentHashMap<>();
    private final Map<String, AtomicLong> seq = new ConcurrentHashMap<>();

    @Override
    public synchronized StreamMessage append(String threadId, String role, List<Map<String, Object>> blocks) {
        long sequence = seq.computeIfAbsent(threadId, key -> new AtomicLong()).incrementAndGet();
        StreamMessage message = new StreamMessage(
                "msg_" + stripThread(threadId) + "_" + sequence,
                threadId,
                sequence,
                role,
                OffsetDateTime.now().toString(),
                blocks);
        events.computeIfAbsent(threadId, key -> new ArrayList<>()).add(message);
        return message;
    }

    @Override
    public synchronized List<StreamMessage> history(String threadId) {
        List<StreamMessage> list = events.get(threadId);
        return list == null ? List.of() : new ArrayList<>(list);
    }

    private String stripThread(String threadId) {
        return threadId.startsWith("thread_") ? threadId.substring("thread_".length()) : threadId;
    }
}
