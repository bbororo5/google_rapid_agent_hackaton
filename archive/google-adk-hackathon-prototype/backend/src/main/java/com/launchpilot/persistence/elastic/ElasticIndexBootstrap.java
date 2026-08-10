package com.launchpilot.persistence.elastic;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.StringReader;
import org.springframework.stereotype.Component;

/** Bootstraps required Elastic indices and mappings. */
@Component
public class ElasticIndexBootstrap {

    private final ElasticsearchClient es;

    public ElasticIndexBootstrap(ElasticsearchClient es) {
        this.es = es;
    }

    @PostConstruct
    public void bootstrap() throws IOException {
        ensureIndex(ElasticIndices.CAMPAIGNS, ElasticIndexMappings.CAMPAIGNS);
        ensureIndex(ElasticIndices.CONTENT_POSTS, ElasticIndexMappings.CONTENT_POSTS);
        ensureIndex(ElasticIndices.GROWTH_BRIEFS, ElasticIndexMappings.GROWTH_BRIEFS);
        ensureIndex(ElasticIndices.CALENDAR_EVENTS, ElasticIndexMappings.CALENDAR_EVENTS);
    }

    private void ensureIndex(String name, String mappingJson) throws IOException {
        boolean exists = es.indices().exists(e -> e.index(name)).value();
        if (!exists) {
            es.indices().create(c -> c.index(name).withJson(new StringReader(mappingJson)));
        }
    }
}
