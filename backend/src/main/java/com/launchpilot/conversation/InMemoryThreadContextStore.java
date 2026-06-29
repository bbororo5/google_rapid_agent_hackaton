package com.launchpilot.conversation;

import com.launchpilot.importing.ImportThreadRegistry;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * In-memory routing context for active conversation threads.
 * Elastic remains the durable source of business data; this store only keeps
 * transient workspace/campaign routing for Java-owned live threads.
 */
@Component
public class InMemoryThreadContextStore implements ThreadContextStore, ImportThreadRegistry {

    private final Map<String, RunContext> store = new ConcurrentHashMap<>();
    private volatile RunContext last;
    private final String demoWorkspaceId;
    private final String demoCampaignId;

    public InMemoryThreadContextStore(
            @Value("${launchpilot.demo.workspace-id:demo_workspace}") String demoWorkspaceId,
            @Value("${launchpilot.demo.campaign-id:camp_comeback_teaser}") String demoCampaignId) {
        this.demoWorkspaceId = demoWorkspaceId;
        this.demoCampaignId = demoCampaignId;
    }

    @Override
    public void register(String threadId, RunContext context) {
        store.put(threadId, context);
        last = context;
    }

    @Override
    public void registerImportedThread(String threadId, String workspaceId, String campaignId) {
        register(threadId, new RunContext(workspaceId, campaignId));
    }

    @Override
    public RunContext resolveOrCreate(String threadId) {
        return get(threadId).orElseGet(() -> {
            RunContext context = Optional.ofNullable(last)
                    .orElseGet(() -> new RunContext(demoWorkspaceId, demoCampaignId));
            register(threadId, context);
            return context;
        });
    }

    @Override
    public Optional<RunContext> get(String threadId) {
        return Optional.ofNullable(store.get(threadId));
    }
}
