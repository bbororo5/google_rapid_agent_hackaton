package com.launchpilot.service;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * 게이트웨이 코디네이션 상태 (비즈니스 상태 아님).
 * 승인 시 growth_brief/calendar_event 문서는 workspace_id/campaign_id를 요구한다.
 * CSV import가 만든 thread_id와 workspace/campaign 맥락을 메모리에 보관한다.
 * 진실의 원천은 여전히 Elastic. 이 맵은 진행 중 thread의 일시적 라우팅 정보일 뿐이다.
 */
@Component
public class AgentThreadRegistry {

    public record RunContext(String workspaceId, String campaignId) {}

    private final Map<String, RunContext> store = new ConcurrentHashMap<>();

    /**
     * Store or replace the routing context for the given thread ID in the registry.
     *
     * If an entry already exists for the provided `threadId`, it is replaced with `ctx`.
     *
     * @param threadId the identifier of the thread used as the registry key
     * @param ctx the routing context containing `workspaceId` and `campaignId`
     */
    public void put(String threadId, RunContext ctx) {
        store.put(threadId, ctx);
    }

    /**
     * Retrieve the routing RunContext associated with the given thread identifier.
     *
     * @param threadId the thread id used as the registry key
     * @return an Optional containing the RunContext for the given threadId, or `Optional.empty()` if no entry exists
     */
    public Optional<RunContext> get(String threadId) {
        return Optional.ofNullable(store.get(threadId));
    }
}
