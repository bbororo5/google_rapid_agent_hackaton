package com.launchpilot.persistence.elastic;

import com.launchpilot.dto.elastic.CampaignDoc;

/** Persistence port for campaign working context documents. */
public interface CampaignRepository {
    void upsertCampaign(CampaignDoc campaign);
}
