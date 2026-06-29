package com.launchpilot.persistence.elastic;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.Refresh;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;
import com.launchpilot.dto.elastic.ContentPostDoc;
import com.launchpilot.service.ApiException;
import java.io.IOException;
import java.util.List;
import org.springframework.stereotype.Component;

/** Elastic-backed repository for imported content evidence rows. */
@Component
public class ElasticContentPostRepository implements ContentPostRepository {

    private final ElasticsearchClient es;

    public ElasticContentPostRepository(ElasticsearchClient es) {
        this.es = es;
    }

    @Override
    public IndexResult bulkIndex(List<ContentPostDoc> posts) {
        if (posts.isEmpty()) {
            return new IndexResult(0, 0);
        }
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
            return new IndexResult(posts.size() - failed, failed);
        } catch (IOException e) {
            throw ApiException.internal("content_posts indexing failed: " + e.getMessage());
        }
    }
}
