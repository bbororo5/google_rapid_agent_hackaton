package com.launchpilot.service;

import com.launchpilot.client.ElasticDocumentWriter;
import com.launchpilot.dto.common.Channel;
import com.launchpilot.dto.elastic.CampaignDoc;
import com.launchpilot.dto.elastic.ContentPostDoc;
import com.launchpilot.dto.pub.ImportCsvResponse;
import java.io.IOException;
import java.io.InputStream;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

/**
 * CSV -> content_posts 정규화 + 벌크 색인 (계약 03).
 * AI 없음. 단순 정규화 후 즉시 색인 (refresh=true).
 */
@Service
public class ImportService {

    private static final Set<String> NON_METRIC_COLUMNS =
            Set.of("post_id", "published_at", "channel", "title", "permalink");

    private final CsvStreamingParser parser;
    private final ElasticDocumentWriter writer;
    private final IdGenerator ids;
    private final AgentThreadRegistry registry;

    /**
     * Constructs an ImportService with the components required to parse CSV input,
     * convert rows to documents, and write documents to Elasticsearch.
     *
     * @param parser CSV streaming parser used to iterate rows and obtain the header
     * @param writer writer responsible for bulk-indexing ContentPostDoc documents
     * @param ids generator for import IDs and fallback post IDs
     */
    public ImportService(CsvStreamingParser parser, ElasticDocumentWriter writer, IdGenerator ids, AgentThreadRegistry registry) {
        this.parser = parser;
        this.writer = writer;
        this.ids = ids;
        this.registry = registry;
    }

    /**
     * Ingests a CSV stream, normalizes each row into ContentPostDoc documents, bulk-indexes them, and returns import results and metadata.
     *
     * @param csv           the InputStream containing the CSV data to ingest
     * @param filename      the original filename associated with the CSV
     * @param workspaceId   the workspace identifier to associate with created documents
     * @param campaignId    the campaign identifier to associate with created documents
     * @param sourcePlatform the fallback Channel to use when a row's channel value is missing or invalid
     * @return              an ImportCsvResponse containing the import success flag, generated import ID, workspace and campaign IDs, counts of indexed and failed documents, the CSV header columns, and the ingestion timestamp
     * @throws ApiException if CSV reading/parsing fails (bad request) or if bulk indexing fails (internal error)
     */
    public ImportCsvResponse importCsv(
            InputStream csv,
            String filename,
            String workspaceId,
            String campaignId,
            Channel sourcePlatform) {

        String importId = ids.newImportId();
        String threadId = "thread_" + importId.substring("imp_".length());
        registry.put(threadId, new AgentThreadRegistry.RunContext(workspaceId, campaignId));
        String ingestedAt = OffsetDateTime.now().toString();
        List<ContentPostDoc> docs = new ArrayList<>();

        CsvStreamingParser.Header header;
        try {
            header = parser.parse(csv, (rowNumber, row) ->
                    docs.add(toDoc(row, rowNumber, importId, filename, workspaceId, campaignId,
                            sourcePlatform, ingestedAt)));
        } catch (IOException e) {
            throw ApiException.badRequest("CSV read failed: " + e.getMessage());
        }

        ElasticDocumentWriter.IndexResult result;
        try {
            writer.upsertCampaign(toCampaignDoc(workspaceId, campaignId, ingestedAt));
            result = writer.bulkIndexContentPosts(docs);
        } catch (IOException e) {
            throw ApiException.internal("campaign/content_posts indexing failed: " + e.getMessage());
        }

        return new ImportCsvResponse(
                true,
                importId,
                workspaceId,
                campaignId,
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

    /**
     * Convert a CSV row into a ContentPostDoc with normalized fields and parsed numeric metrics.
     *
     * @param row           a map of CSV column names to raw string values for the row
     * @param rowNumber     1-based row number within the CSV (used when generating fallback IDs and source metadata)
     * @param importId      import-level identifier to associate with the produced document
     * @param filename      original CSV filename used in the document's source metadata
     * @param workspaceId   workspace identifier to set on the document
     * @param campaignId    campaign identifier to set on the document
     * @param sourcePlatform fallback Channel used when the row's channel value is missing or invalid
     * @param ingestedAt    ingestion timestamp applied when a row's published_at is missing
     * @return              a ContentPostDoc containing:
     *                      - a resolved or generated postId,
     *                      - resolved channel,
     *                      - publishedAt (defaults to ingestedAt when blank),
     *                      - title (defaults to postId when blank),
     *                      - a map of parsed numeric metrics (preserving column order),
     *                      - Source metadata (importId, filename, rowNumber),
     *                      - a copy of the original row map,
     *                      - the ingestedAt timestamp
     */
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
        for (Map.Entry<String, String> e : row.entrySet()) {
            if (NON_METRIC_COLUMNS.contains(e.getKey())) {
                continue;
            }
            Double num = tryParseDouble(e.getValue());
            if (num != null) {
                metrics.put(e.getKey(), num);
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

    /**
     * Resolve a channel identifier string to a Channel enum, using a fallback when necessary.
     *
     * @param raw      raw channel value; may be null or blank
     * @param fallback fallback Channel to use when {@code raw} is null, blank, or unrecognized; may be null
     * @return the Channel parsed from {@code raw} when valid; {@code fallback} if {@code raw} is null/blank/unrecognized; {@code Channel.UNKNOWN} if both {@code raw} is invalid and {@code fallback} is null
     */
    private Channel resolveChannel(String raw, Channel fallback) {
        String v = blankToNull(raw);
        if (v != null) {
            try {
                return Channel.from(v);
            } catch (IllegalArgumentException ignored) {
                // 알 수 없는 채널 값 -> fallback
            }
        }
        return fallback != null ? fallback : Channel.UNKNOWN;
    }

    /**
     * Normalize a string value: produce `null` when the input is `null` or contains only whitespace, otherwise return the trimmed input.
     *
     * @param s the input string that may be `null` or blank
     * @return `null` if `s` is `null` or blank, otherwise `s.trim()`
     */
    private static String blankToNull(String s) {
        return (s == null || s.isBlank()) ? null : s.trim();
    }

    /**
     * Parses a trimmed decimal value from the given string.
     *
     * @param s the input string to parse; may be null or blank
     * @return the parsed Double value, or null if the input is null, blank, or not a valid number
     */
    private static Double tryParseDouble(String s) {
        if (s == null || s.isBlank()) {
            return null;
        }
        try {
            return Double.parseDouble(s.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
