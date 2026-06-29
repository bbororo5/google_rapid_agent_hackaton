package com.launchpilot.persistence.elastic;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.Refresh;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import com.launchpilot.contracts.elastic.CalendarEventDoc;
import com.launchpilot.contracts.elastic.GrowthBriefDoc;
import com.launchpilot.common.ApiException;
import java.io.IOException;
import java.util.List;
import org.springframework.stereotype.Component;

/** Elastic-backed repository for approved immutable business documents. */
@Component
public class ElasticApprovalDocumentRepository implements ApprovalDocumentRepository {

    private final ElasticsearchClient es;

    public ElasticApprovalDocumentRepository(ElasticsearchClient es) {
        this.es = es;
    }

    @Override
    public boolean growthBriefExistsForThread(String threadId) {
        try {
            long count = es.count(c -> c.index(ElasticIndices.GROWTH_BRIEFS)
                    .query(q -> q.term(t -> t.field("thread_id").value(threadId))))
                    .count();
            return count > 0;
        } catch (IOException e) {
            throw ApiException.internal("approval idempotency check failed: " + e.getMessage());
        }
    }

    @Override
    public void persistApproval(GrowthBriefDoc brief, List<CalendarEventDoc> events) {
        try {
            BulkRequest.Builder request = new BulkRequest.Builder().refresh(Refresh.True);
            request.operations(op -> op.index(i -> i
                    .index(ElasticIndices.GROWTH_BRIEFS)
                    .id(brief.growthBriefId())
                    .document(brief)));
            for (CalendarEventDoc event : events) {
                request.operations(op -> op.index(i -> i
                        .index(ElasticIndices.CALENDAR_EVENTS)
                        .id(event.eventId())
                        .document(event)));
            }
            BulkResponse response = es.bulk(request.build());
            if (response.errors()) {
                String firstError = response.items().stream()
                        .filter(item -> item.error() != null)
                        .map(item -> item.error().reason())
                        .findFirst()
                        .orElse("unknown bulk error");
                throw ApiException.internal("approval persistence failed: " + firstError);
            }
        } catch (IOException e) {
            throw ApiException.internal("approval persistence failed: " + e.getMessage());
        }
    }
}
