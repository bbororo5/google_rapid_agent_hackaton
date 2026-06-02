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

    public ElasticDocumentWriter(ElasticsearchClient es) {
        this.es = es;
    }

    @PostConstruct
    public void bootstrap() throws IOException {
        ensureIndex(CONTENT_POSTS, CONTENT_POSTS_MAPPING);
        ensureIndex(GROWTH_BRIEFS, GROWTH_BRIEFS_MAPPING);
        ensureIndex(CALENDAR_EVENTS, CALENDAR_EVENTS_MAPPING);
    }

    private void ensureIndex(String name, String mappingJson) throws IOException {
        boolean exists = es.indices().exists(e -> e.index(name)).value();
        if (!exists) {
            es.indices().create(c -> c.index(name).withJson(new StringReader(mappingJson)));
        }
    }

    /** content_posts upsert. 부분 실패 허용 -> indexed/failed 카운트 반환. */
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

    /** 같은 agent_run_id로 이미 승인된 브리프 존재 여부 (1회성 승인 검사). */
    public boolean growthBriefExistsForRun(String agentRunId) throws IOException {
        long count = es.count(c -> c.index(GROWTH_BRIEFS)
                .query(q -> q.term(t -> t.field("agent_run_id").value(agentRunId))))
                .count();
        return count > 0;
    }

    /** 승인 영속화: growth_brief 1건 + calendar_event N건. all-or-fail. */
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
