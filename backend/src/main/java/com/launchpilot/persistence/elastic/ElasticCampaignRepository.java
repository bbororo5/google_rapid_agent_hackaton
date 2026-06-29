package com.launchpilot.persistence.elastic;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.Refresh;
import com.launchpilot.dto.elastic.CampaignDoc;
import com.launchpilot.common.ApiException;
import java.io.IOException;
import org.springframework.stereotype.Component;

/** Elastic-backed campaign working context repository. */
@Component
public class ElasticCampaignRepository implements CampaignRepository {

    private final ElasticsearchClient es;

    public ElasticCampaignRepository(ElasticsearchClient es) {
        this.es = es;
    }

    @Override
    public void upsertCampaign(CampaignDoc campaign) {
        try {
            es.index(i -> i.index(ElasticIndices.CAMPAIGNS)
                    .id(campaign.campaignId())
                    .document(campaign)
                    .refresh(Refresh.True));
        } catch (IOException e) {
            throw ApiException.internal("campaign indexing failed: " + e.getMessage());
        }
    }
}
