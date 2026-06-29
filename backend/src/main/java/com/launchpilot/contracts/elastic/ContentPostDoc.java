package com.launchpilot.contracts.elastic;

import com.launchpilot.contracts.shared.Channel;
import java.util.Map;

public record ContentPostDoc(
        String postId,
        String workspaceId,
        String campaignId,
        Channel channel,
        String publishedAt,
        String title,
        String permalink,
        Map<String, Double> metrics,
        Source source,
        Map<String, Object> raw,
        String ingestedAt) {

    public record Source(String importId, String filename, int rowNumber) {}
}
