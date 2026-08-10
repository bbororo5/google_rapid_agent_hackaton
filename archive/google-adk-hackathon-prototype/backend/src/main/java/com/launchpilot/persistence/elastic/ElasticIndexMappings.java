package com.launchpilot.persistence.elastic;

/** Index mappings for the Elastic business/evidence store. */
final class ElasticIndexMappings {
    static final String CAMPAIGNS = """
            {
              "mappings": {
                "properties": {
                  "campaign_id": {"type": "keyword"},
                  "workspace_id": {"type": "keyword"},
                  "name": {"type": "text"},
                  "description": {"type": "text"},
                  "primary_channels": {"type": "keyword"},
                  "target_metrics": {"type": "keyword"},
                  "date_range": {"type": "object"},
                  "brand_name": {"type": "keyword"},
                  "goals": {"type": "text"},
                  "constraints": {"type": "text"},
                  "created_at": {"type": "date"},
                  "updated_at": {"type": "date"}
                }
              }
            }
            """;

    static final String CONTENT_POSTS = """
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

    static final String GROWTH_BRIEFS = """
            {
              "mappings": {
                "properties": {
                  "growth_brief_id": {"type": "keyword"},
                  "workspace_id": {"type": "keyword"},
                  "campaign_id": {"type": "keyword"},
                  "thread_id": {"type": "keyword"},
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

    static final String CALENDAR_EVENTS = """
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

    private ElasticIndexMappings() {}
}
