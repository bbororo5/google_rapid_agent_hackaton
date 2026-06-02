package com.launchpilot.client;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.Refresh;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;
import com.launchpilot.dto.elastic.CalendarEventDoc;
import com.launchpilot.dto.elastic.ContentPostDoc;
import com.launchpilot.dto.elastic.GrowthBriefDoc;
import com.launchpilot.service.ApiException;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * 계약 03 Elastic 쓰기. 유일 데이터 저장소.
 * 부트스트랩: 인덱스 3종 매핑 멱등 생성.
 * 승인 쓰기: refresh=true, all-or-fail.
 */
@Component
public class ElasticDocumentWriter {

    public static final String CONTENT_POSTS = "content_posts";
    public static final String GROWTH_BRIEFS = "growth_briefs";
    public static final String CALENDAR_EVENTS = "calendar_events";

    private final ElasticsearchClient es;

    /**
     * Create an ElasticDocumentWriter backed by the given Elasticsearch client.
     *
     * @param es the Elasticsearch client used for index management and document operations
     */
    public ElasticDocumentWriter(ElasticsearchClient es) {
        this.es = es;
    }

    /**
     * Ensures the application's Elasticsearch indices (CONTENT_POSTS, GROWTH_BRIEFS, CALENDAR_EVENTS) exist and creates any missing index using its mapping.
     *
     * @throws IOException if an I/O error occurs while checking or creating indices
     */
    @PostConstruct
    public void bootstrap() throws IOException {
        ensureIndex(CONTENT_POSTS, CONTENT_POSTS_MAPPING);
        ensureIndex(GROWTH_BRIEFS, GROWTH_BRIEFS_MAPPING);
        ensureIndex(CALENDAR_EVENTS, CALENDAR_EVENTS_MAPPING);
    }

    /**
     * Ensure the Elasticsearch index with the given name exists, creating it with the provided mapping if missing.
     *
     * @param name        the target index name
     * @param mappingJson the index mapping as a JSON string to use when creating the index
     * @throws IOException if an I/O error occurs while communicating with Elasticsearch
     */
    private void ensureIndex(String name, String mappingJson) throws IOException {
        boolean exists = es.indices().exists(e -> e.index(name)).value();
        if (!exists) {
            es.indices().create(c -> c.index(name).withJson(new StringReader(mappingJson)));
        }
    }

    /**
     * Bulk indexes multiple content post documents, allowing partial failures.
     *
     * If `docs` is empty this method returns an `IndexResult` with zeros without contacting Elasticsearch.
     *
     * @param docs the list of content post documents to index
     * @return an IndexResult where `indexed` is the number of successfully indexed documents and `failed` is the number of per-item failures
     * @throws IOException if an I/O error occurs while communicating with Elasticsearch
     */
    public IndexResult bulkIndexContentPosts(List<ContentPostDoc> docs) throws IOException {
        if (docs.isEmpty()) {
            return new IndexResult(0, 0);
        }
        BulkRequest.Builder br = new BulkRequest.Builder().refresh(Refresh.True);
        for (ContentPostDoc d : docs) {
            br.operations(op -> op.index(i -> i.index(CONTENT_POSTS).id(d.postId()).document(d)));
        }
        BulkResponse resp = es.bulk(br.build());
        int failed = 0;
        for (BulkResponseItem item : resp.items()) {
            if (item.error() != null) {
                failed++;
            }
        }
        return new IndexResult(docs.size() - failed, failed);
    }

    /**
     * Checks whether a growth brief with the given agent run id already exists.
     *
     * @param agentRunId the agent run identifier to match
     * @return `true` if at least one growth brief exists for the given agent run id, `false` otherwise
     * @throws IOException if an I/O error occurs while querying Elasticsearch
     */
    public boolean growthBriefExistsForRun(String agentRunId) throws IOException {
        long count = es.count(c -> c.index(GROWTH_BRIEFS)
                .query(q -> q.term(t -> t.field("agent_run_id").value(agentRunId))))
                .count();
        return count > 0;
    }

    /**
     * Persist a growth brief and its associated calendar events in a single bulk operation.
     *
     * The method performs an all-or-fail bulk index: if any item-level error is reported by Elasticsearch,
     * an internal ApiException is thrown and no partial success is considered accepted.
     *
     * @param brief  the growth brief document to index
     * @param events the list of calendar event documents to index
     * @throws IOException  if an I/O error occurs communicating with Elasticsearch
     * @throws ApiException if the bulk response contains item-level errors (message contains the first error reason)
     */
    public void persistApproval(GrowthBriefDoc brief, List<CalendarEventDoc> events)
            throws IOException {
        BulkRequest.Builder br = new BulkRequest.Builder().refresh(Refresh.True);
        br.operations(op -> op.index(
                i -> i.index(GROWTH_BRIEFS).id(brief.growthBriefId()).document(brief)));
        for (CalendarEventDoc ev : events) {
            br.operations(op -> op.index(
                    i -> i.index(CALENDAR_EVENTS).id(ev.eventId()).document(ev)));
        }
        BulkResponse resp = es.bulk(br.build());
        if (resp.errors()) {
            String firstError = resp.items().stream()
                    .filter(it -> it.error() != null)
                    .map(it -> it.error().reason())
                    .findFirst()
                    .orElse("unknown bulk error");
            throw ApiException.internal("approval persistence failed: " + firstError);
        }
    }

    public record IndexResult(int indexed, int failed) {}

    private static final String CONTENT_POSTS_MAPPING = """
            {
              "mappings": {
                "properties": {
                  "post_id": {"type": "keyword"},
                  "workspace_id": {"type": "keyword"},
                  "campaign_id": {"type": "keyword"},
                  "channel": {"type": "keyword"},
                  "published_at": {"type": "date"},
                  "title": {"type": "text"},
                  "permalink": {"type": "keyword"},
                  "metrics": {"type": "object"},
                  "source": {"type": "object"},
                  "raw": {"type": "object", "enabled": false},
                  "ingested_at": {"type": "date"}
                }
              }
            }
            """;

    private static final String GROWTH_BRIEFS_MAPPING = """
            {
              "mappings": {
                "properties": {
                  "growth_brief_id": {"type": "keyword"},
                  "workspace_id": {"type": "keyword"},
                  "campaign_id": {"type": "keyword"},
                  "agent_run_id": {"type": "keyword"},
                  "experiment_plan_id": {"type": "keyword"},
                  "approved_by": {"type": "keyword"},
                  "approved_at": {"type": "date"},
                  "summary": {"type": "text"},
                  "signals": {"type": "object", "enabled": false},
                  "hypotheses": {"type": "object", "enabled": false},
                  "final_experiments": {"type": "object", "enabled": false},
                  "source_evidence_refs": {"type": "keyword"},
                  "calendar_event_ids": {"type": "keyword"},
                  "version": {"type": "integer"},
                  "created_at": {"type": "date"}
                }
              }
            }
            """;

    private static final String CALENDAR_EVENTS_MAPPING = """
            {
              "mappings": {
                "properties": {
                  "event_id": {"type": "keyword"},
                  "growth_brief_id": {"type": "keyword"},
                  "experiment_id": {"type": "keyword"},
                  "workspace_id": {"type": "keyword"},
                  "campaign_id": {"type": "keyword"},
                  "title": {"type": "text"},
                  "channel": {"type": "keyword"},
                  "scheduled_at": {"type": "date"},
                  "target_metric": {"type": "keyword"},
                  "success_criteria": {"type": "text"},
                  "production_brief": {"type": "text"},
                  "created_at": {"type": "date"}
                }
              }
            }
            """;
}
