package com.launchpilot.importing;

import com.launchpilot.contracts.shared.Channel;
import java.io.InputStream;

/** Transport-neutral command for importing one CSV file. */
public record CsvImportCommand(
        InputStream csv,
        String filename,
        String workspaceId,
        String campaignId,
        Channel sourcePlatform) {}
