package com.launchpilot.importing;

import com.launchpilot.conversation.RunContext;
import com.launchpilot.conversation.ThreadContextStore;
import com.launchpilot.contracts.shared.Channel;
import com.launchpilot.contracts.elastic.CampaignDoc;
import com.launchpilot.contracts.elastic.ContentPostDoc;
import com.launchpilot.contracts.frontend.ImportCsvResponse;
import com.launchpilot.persistence.elastic.CampaignRepository;
import com.launchpilot.persistence.elastic.ContentPostRepository;
import com.launchpilot.persistence.elastic.IndexResult;
import com.launchpilot.common.ApiException;
import com.launchpilot.common.IdGenerator;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

/**
 * CSV -> content_posts normalization + campaign bootstrap.
 */
@Service
public class CsvImportService implements ImportUseCase {

    private static final Set<String> NON_METRIC_COLUMNS =
            Set.of("post_id", "published_at", "channel", "title", "permalink");

    private final CsvStreamingParser parser;
    private final CampaignRepository campaigns;
    private final ContentPostRepository contentPosts;
    private final IdGenerator ids;
    private final ThreadContextStore threadContexts;

    public CsvImportService(
            CsvStreamingParser parser,
            CampaignRepository campaigns,
            ContentPostRepository contentPosts,
            IdGenerator ids,
            ThreadContextStore threadContexts) {
        this.parser = parser;
        this.campaigns = campaigns;
        this.contentPosts = contentPosts;
        this.ids = ids;
        this.threadContexts = threadContexts;
    }

    @Override
    public ImportCsvResponse importCsv(CsvImportCommand command) {
        String importId = ids.newImportId();
        String threadId = "thread_" + importId.substring("imp_".length());
        threadContexts.register(threadId, new RunContext(command.workspaceId(), command.campaignId()));
        String ingestedAt = OffsetDateTime.now().toString();
        List<ContentPostDoc> docs = new ArrayList<>();

        CsvStreamingParser.Header header;
        try {
            header = parser.parse(command.csv(), (rowNumber, row) ->
                    docs.add(toDoc(row, rowNumber, importId, command.filename(), command.workspaceId(),
                            command.campaignId(), command.sourcePlatform(), ingestedAt)));
        } catch (IOException e) {
            throw ApiException.badRequest("CSV read failed: " + e.getMessage());
        }

        campaigns.upsertCampaign(toCampaignDoc(command.workspaceId(), command.campaignId(), ingestedAt));
        IndexResult result = contentPosts.bulkIndex(docs);

        return new ImportCsvResponse(
                true,
                importId,
                command.workspaceId(),
                command.campaignId(),
                result.indexed(),
                result.failed(),
                header.columns(),
                ingestedAt);
    }

    private CampaignDoc toCampaignDoc(String workspaceId, String campaignId, String timestamp) {
        return new CampaignDoc(
                campaignId,
                workspaceId,
                "Comeback Teaser",
                "Demo campaign working context for metric analysis and experiment planning.",
                List.of("tiktok", "instagram", "youtube"),
                List.of("save_rate", "retention_rate", "shares"),
                Map.of("start", "2026-06-01", "end", "2026-06-30"),
                timestamp,
                timestamp,
                "LaunchPilot Demo",
                List.of("Find repeatable content signals", "Plan 1-2 experiments for next week"),
                List.of("Use imported campaign evidence", "Require human approval before persistence"));
    }

    private ContentPostDoc toDoc(
            Map<String, String> row,
            int rowNumber,
            String importId,
            String filename,
            String workspaceId,
            String campaignId,
            Channel sourcePlatform,
            String ingestedAt) {

        String postId = blankToNull(row.get("post_id"));
        if (postId == null) {
            postId = ids.postId(importId, rowNumber);
        }

        Channel channel = resolveChannel(row.get("channel"), sourcePlatform);

        String publishedAt = blankToNull(row.get("published_at"));
        if (publishedAt == null) {
            publishedAt = ingestedAt;
        }

        String title = blankToNull(row.get("title"));
        if (title == null) {
            title = postId;
        }

        Map<String, Double> metrics = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : row.entrySet()) {
            if (NON_METRIC_COLUMNS.contains(entry.getKey())) {
                continue;
            }
            Double num = tryParseDouble(entry.getValue());
            if (num != null) {
                metrics.put(entry.getKey(), num);
            }
        }

        ContentPostDoc.Source source =
                new ContentPostDoc.Source(importId, filename, rowNumber);

        return new ContentPostDoc(
                postId,
                workspaceId,
                campaignId,
                channel,
                publishedAt,
                title,
                blankToNull(row.get("permalink")),
                metrics,
                source,
                new LinkedHashMap<>(row),
                ingestedAt);
    }

    private Channel resolveChannel(String raw, Channel fallback) {
        String value = blankToNull(raw);
        if (value != null) {
            try {
                return Channel.from(value);
            } catch (IllegalArgumentException ignored) {
                // Unknown CSV channel value falls back to request metadata.
            }
        }
        return fallback != null ? fallback : Channel.UNKNOWN;
    }

    private static String blankToNull(String value) {
        return (value == null || value.isBlank()) ? null : value.trim();
    }

    private static Double tryParseDouble(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return Double.parseDouble(value.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
