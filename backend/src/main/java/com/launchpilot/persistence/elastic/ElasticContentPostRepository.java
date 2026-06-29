package com.launchpilot.persistence.elastic;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.Refresh;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;
import com.launchpilot.contracts.elastic.ContentPostDoc;
import com.launchpilot.importing.ContentPostRepository;
import com.launchpilot.importing.IndexResult;
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

/** Elastic-backed repository for imported content evidence rows. */
@Component
public class ElasticContentPostRepository implements ContentPostRepository {

    private final ElasticsearchClient es;
    private final ObservabilityGateway observability;

    public ElasticContentPostRepository(ElasticsearchClient es, ObservabilityGateway observability) {
        this.es = es;
        this.observability = observability;
    }

    @Override
    public IndexResult bulkIndex(List<ContentPostDoc> posts) {
        if (posts.isEmpty()) {
            return new IndexResult(0, 0);
        }
        ContentPostDoc first = posts.getFirst();
        Map<String, Object> attributes = Map.of(
                "index", ElasticIndices.CONTENT_POSTS,
                "document_count", posts.size(),
                "workspace_id", first.workspaceId(),
                "campaign_id", first.campaignId());
        try (ObservationScope scope = observability.startOperation(
                new ObservedOperation("elastic.content_posts.bulk_index", OperationKind.ELASTIC_WRITE, attributes),
                correlation(first.postId(), null, first.workspaceId(), first.campaignId(), "content_posts_bulk_index"))) {
            try {
                BulkRequest.Builder request = new BulkRequest.Builder().refresh(Refresh.True);
                for (ContentPostDoc post : posts) {
                    request.operations(op -> op.index(i -> i
                            .index(ElasticIndices.CONTENT_POSTS)
                            .id(post.postId())
                            .document(post)));
                }
                BulkResponse response = es.bulk(request.build());
                int failed = 0;
                for (BulkResponseItem item : response.items()) {
                    if (item.error() != null) {
                        failed++;
                    }
                }
                IndexResult result = new IndexResult(posts.size() - failed, failed);
                scope.markSuccess(Map.of(
                        "indexed_count", result.indexed(),
                        "failed_count", result.failed()));
                return result;
            } catch (IOException e) {
                ApiException error = ApiException.internal("content_posts indexing failed: " + e.getMessage());
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
