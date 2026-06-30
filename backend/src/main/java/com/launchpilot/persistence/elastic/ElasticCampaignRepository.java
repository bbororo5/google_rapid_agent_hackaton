package com.launchpilot.persistence.elastic;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.Refresh;
import com.launchpilot.contracts.elastic.CampaignDoc;
import com.launchpilot.importing.CampaignRepository;
import com.launchpilot.common.ApiException;
import com.launchpilot.observability.CorrelationContext;
import com.launchpilot.observability.ObservabilityGateway;
import com.launchpilot.observability.ObservationScope;
import com.launchpilot.observability.ObservedOperation;
import com.launchpilot.observability.OperationKind;
import java.io.IOException;
import java.util.Map;
import org.springframework.stereotype.Component;

/** Elastic-backed campaign working context repository. */
@Component
public class ElasticCampaignRepository implements CampaignRepository {

    private final ElasticsearchClient es;
    private final ObservabilityGateway observability;

    public ElasticCampaignRepository(ElasticsearchClient es, ObservabilityGateway observability) {
        this.es = es;
        this.observability = observability;
    }

    @Override
    public void upsertCampaign(CampaignDoc campaign) {
        Map<String, Object> attributes = Map.of(
                "index", ElasticIndices.CAMPAIGNS,
                "campaign_id", campaign.campaignId(),
                "workspace_id", campaign.workspaceId());
        try (ObservationScope scope = observability.startOperation(
                new ObservedOperation("elastic.campaign.upsert", OperationKind.ELASTIC_WRITE, attributes),
                correlation(campaign.campaignId(), null, campaign.workspaceId(), campaign.campaignId(), "campaign_upsert"))) {
            try {
                es.index(i -> i.index(ElasticIndices.CAMPAIGNS)
                        .id(campaign.campaignId())
                        .document(campaign)
                        .refresh(Refresh.True));
                scope.markSuccess(attributes);
            } catch (IOException e) {
                ApiException error = ApiException.internal("campaign indexing failed: " + e.getMessage());
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
                threadId,
                workspaceId,
                campaignId,
                "persistence.elastic",
                operation);
    }
}
