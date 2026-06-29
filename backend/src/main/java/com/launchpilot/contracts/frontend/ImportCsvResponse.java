package com.launchpilot.contracts.frontend;

import java.util.List;

public record ImportCsvResponse(
        boolean ok,
        String importId,
        String workspaceId,
        String campaignId,
        int indexedCount,
        int failedCount,
        List<String> columns,
        String createdAt) {}
