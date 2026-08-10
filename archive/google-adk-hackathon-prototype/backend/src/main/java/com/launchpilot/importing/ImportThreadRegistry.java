package com.launchpilot.importing;

/** Registers the conversation context created by a successful import. */
public interface ImportThreadRegistry {
    void registerImportedThread(String threadId, String workspaceId, String campaignId);
}
