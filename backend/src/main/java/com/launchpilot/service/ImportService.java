package com.launchpilot.service;

import com.launchpilot.client.ElasticDocumentWriter;
import com.launchpilot.dto.common.Channel;
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

    public ImportService(CsvStreamingParser parser, ElasticDocumentWriter writer, IdGenerator ids) {
        this.parser = parser;
        this.writer = writer;
        this.ids = ids;
    }

    public ImportCsvResponse importCsv(
            InputStream csv,
            String filename,
            String workspaceId,
            String campaignId,
            Channel sourcePlatform) {

        String importId = ids.newImportId();
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
            result = writer.bulkIndexContentPosts(docs);
        } catch (IOException e) {
            throw ApiException.internal("content_posts indexing failed: " + e.getMessage());
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

    private static String blankToNull(String s) {
        return (s == null || s.isBlank()) ? null : s.trim();
    }

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
