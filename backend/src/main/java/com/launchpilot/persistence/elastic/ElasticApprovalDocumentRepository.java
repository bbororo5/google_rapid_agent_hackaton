package com.launchpilot.persistence.elastic;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.Refresh;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import com.launchpilot.contracts.elastic.CalendarEventDoc;
import com.launchpilot.contracts.elastic.GrowthBriefDoc;
import com.launchpilot.common.ApiException;
import com.launchpilot.observability.CorrelationContext;
import com.launchpilot.observability.ObservabilityGateway;
import com.launchpilot.observability.ObservationScope;
import com.launchpilot.observability.ObservedOperation;
import com.launchpilot.observability.OperationKind;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/** Elastic-backed repository for approved immutable business documents. */
@Component
public class ElasticApprovalDocumentRepository implements ApprovalDocumentRepository {

    private final ElasticsearchClient es;
    private final ObservabilityGateway observability;

    public ElasticApprovalDocumentRepository(ElasticsearchClient es, ObservabilityGateway observability) {
        this.es = es;
        this.observability = observability;
    }

    @Override
    public boolean growthBriefExistsForThread(String threadId) {
        Map<String, Object> attributes = Map.of(
                "index", ElasticIndices.GROWTH_BRIEFS,
                "thread_id", threadId);
        try (ObservationScope scope = observability.startOperation(
                new ObservedOperation("elastic.growth_briefs.exists_for_thread", OperationKind.ELASTIC_READ, attributes),
                correlation(threadId, threadId, null, null, "growth_brief_exists"))) {
            try {
                long count = es.count(c -> c.index(ElasticIndices.GROWTH_BRIEFS)
                        .query(q -> q.term(t -> t.field("thread_id").value(threadId))))
                        .count();
                boolean exists = count > 0;
                scope.markSuccess(Map.of("exists", exists, "count", count));
                return exists;
            } catch (IOException e) {
                ApiException error = ApiException.internal("approval idempotency check failed: " + e.getMessage());
                scope.markFailure(error, attributes);
                throw error;
            } catch (RuntimeException e) {
                scope.markFailure(e, attributes);
                throw e;
            }
        }
    }

    @Override
    public void persistApproval(GrowthBriefDoc brief, List<CalendarEventDoc> events) {
        Map<String, Object> attributes = Map.of(
                "growth_briefs_index", ElasticIndices.GROWTH_BRIEFS,
                "calendar_events_index", ElasticIndices.CALENDAR_EVENTS,
                "growth_brief_id", brief.growthBriefId(),
                "thread_id", brief.threadId(),
                "calendar_event_count", events.size());
        try (ObservationScope scope = observability.startOperation(
                new ObservedOperation("elastic.approval.persist", OperationKind.ELASTIC_WRITE, attributes),
                correlation(brief.growthBriefId(), brief.threadId(), brief.workspaceId(), brief.campaignId(), "approval_persist"))) {
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
                    ApiException error = ApiException.internal("approval persistence failed: " + firstError);
                    scope.markFailure(error, attributes);
                    throw error;
                }
                scope.markSuccess(attributes);
            } catch (IOException e) {
                ApiException error = ApiException.internal("approval persistence failed: " + e.getMessage());
                scope.markFailure(error, attributes);
                throw error;
            } catch (RuntimeException e) {
                scope.markFailure(e, attributes);
                throw e;
            }
        }
    }

    private CorrelationContext correlation(
            String requestId, String threadId, String workspaceId, String campaignId, String operation) {
        return new CorrelationContext(
                requestId,
                requestId,
                threadId,
                workspaceId,
                campaignId,
                "persistence.elastic",
                operation);
    }
}
