package com.launchpilot.conversation;

/** Workspace/campaign scope associated with a live Java thread. */
public record RunContext(String workspaceId, String campaignId) {}
