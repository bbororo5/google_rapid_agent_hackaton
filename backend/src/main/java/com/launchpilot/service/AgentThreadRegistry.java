package com.launchpilot.service;

import com.launchpilot.conversation.RunContext;
import com.launchpilot.conversation.ThreadContextStore;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 게이트웨이 코디네이션 상태 (비즈니스 상태 아님).
 * 승인 시 growth_brief/calendar_event 문서는 workspace_id/campaign_id를 요구한다.
 * CSV import가 만든 thread_id와 workspace/campaign 맥락을 메모리에 보관한다.
 * 진실의 원천은 여전히 Elastic. 이 맵은 진행 중 thread의 일시적 라우팅 정보일 뿐이다.
 */
@Component
public class AgentThreadRegistry implements ThreadContextStore {

    private final Map<String, RunContext> store = new ConcurrentHashMap<>();
    private volatile RunContext last;
    private final String demoWorkspaceId;
    private final String demoCampaignId;

    public AgentThreadRegistry(
            @Value("${launchpilot.demo.workspace-id:demo_workspace}") String demoWorkspaceId,
            @Value("${launchpilot.demo.campaign-id:camp_comeback_teaser}") String demoCampaignId) {
        this.demoWorkspaceId = demoWorkspaceId;
        this.demoCampaignId = demoCampaignId;
    }

    /**
     * Store or replace the routing context for the given thread ID in the registry.
     *
     * If an entry already exists for the provided `threadId`, it is replaced with `ctx`.
     * Also records `ctx` as the most-recent context (see {@link #last()}).
     *
     * @param threadId the identifier of the thread used as the registry key
     * @param ctx the routing context containing `workspaceId` and `campaignId`
     */
    public void put(String threadId, RunContext ctx) {
        register(threadId, ctx);
    }

    @Override
    public void register(String threadId, RunContext ctx) {
        store.put(threadId, ctx);
        last = ctx;
    }

    @Override
    public RunContext resolveOrCreate(String threadId) {
        var existing = get(threadId);
        if (existing.isPresent()) {
            return existing.get();
        }
        RunContext ctx = last().orElseGet(
                () -> new RunContext(demoWorkspaceId, demoCampaignId));
        register(threadId, ctx);
        return ctx;
    }

    /**
     * The most recently registered context (e.g. the latest CSV import), used to
     * bind a live chat thread that was never explicitly registered.
     *
     * @return the last RunContext put into the registry, or empty if none yet
     */
    public Optional<RunContext> last() {
        return Optional.ofNullable(last);
    }

    /**
     * Retrieve the routing RunContext associated with the given thread identifier.
     *
     * @param threadId the thread id used as the registry key
     * @return an Optional containing the RunContext for the given threadId, or `Optional.empty()` if no entry exists
     */
    @Override
    public Optional<RunContext> get(String threadId) {
        return Optional.ofNullable(store.get(threadId));
    }
}
