package com.launchpilot.service;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * 게이트웨이 코디네이션 상태 (비즈니스 상태 아님).
 * 승인 시 growth_brief/calendar_event 문서는 workspace_id/campaign_id를 요구하지만
 * 계약 02 내부 상태 응답에는 없다. 런 시작 시점의 요청 맥락을 메모리에 보관한다.
 * 진실의 원천은 여전히 Elastic. 이 맵은 진행 중 런의 일시적 라우팅 정보일 뿐이다.
 */
@Component
public class AgentRunRegistry {

    public record RunContext(String workspaceId, String campaignId) {}

    private final Map<String, RunContext> store = new ConcurrentHashMap<>();

    public void put(String agentRunId, RunContext ctx) {
        store.put(agentRunId, ctx);
    }

    public Optional<RunContext> get(String agentRunId) {
        return Optional.ofNullable(store.get(agentRunId));
    }
}
