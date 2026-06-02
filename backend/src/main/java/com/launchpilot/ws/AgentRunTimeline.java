package com.launchpilot.ws;

import com.launchpilot.dto.common.AgentStreamServerEvent;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/**
 * 계약 01: 런별 영속(인메모리) 타임라인 + 단조 sequence.
 * 재접속 리플레이(connection.resume/full_sync)의 원천.
 * 단일 인스턴스 가정 (DESIGN.md registry와 동일 전제).
 */
@Component
public class AgentRunTimeline {

    private final Map<String, List<AgentStreamServerEvent>> events = new ConcurrentHashMap<>();
    private final Map<String, AtomicLong> seq = new ConcurrentHashMap<>();

    /**
     * sequence/event_id/occurred_at를 채워 타임라인에 적재하고 완성 이벤트를 반환한다.
     * 영속 타임라인 이벤트(run/agent/message)용. connection.* 제어 이벤트는 적재하지 않는다.
     */
    public synchronized AgentStreamServerEvent commit(String agentRunId, ServerEventBuilder b) {
        long s = seq.computeIfAbsent(agentRunId, k -> new AtomicLong()).incrementAndGet();
        AgentStreamServerEvent event = b
                .agentRunId(agentRunId)
                .sequence(s)
                .eventId("evt_" + stripRun(agentRunId) + "_" + s)
                .occurredAt(OffsetDateTime.now().toString())
                .build();
        events.computeIfAbsent(agentRunId, k -> new ArrayList<>()).add(event);
        return event;
    }

    /** afterSequence 이후의 영속 이벤트 (resume 증분 리플레이용). */
    public synchronized List<AgentStreamServerEvent> eventsAfter(String agentRunId, long afterSequence) {
        List<AgentStreamServerEvent> all = events.get(agentRunId);
        if (all == null) {
            return List.of();
        }
        List<AgentStreamServerEvent> out = new ArrayList<>();
        for (AgentStreamServerEvent e : all) {
            if (e.sequence() != null && e.sequence() > afterSequence) {
                out.add(e);
            }
        }
        return out;
    }

    /** 전체 타임라인 (full_sync 리플레이용). */
    public synchronized List<AgentStreamServerEvent> all(String agentRunId) {
        return new ArrayList<>(events.getOrDefault(agentRunId, List.of()));
    }

    /** 현재 최대 sequence (0 = 비어있음). */
    public long lastSequence(String agentRunId) {
        AtomicLong a = seq.get(agentRunId);
        return a == null ? 0L : a.get();
    }

    private String stripRun(String runId) {
        return runId.startsWith("run_") ? runId.substring("run_".length()) : runId;
    }
}
