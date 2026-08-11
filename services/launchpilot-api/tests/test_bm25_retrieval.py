from datetime import date
from uuid import uuid4

from launchpilot.campaigns.models import Campaign
from launchpilot.campaigns.postgres import PostgresCampaignRepository
from launchpilot.knowledge.contracts.retrieval import (
    CampaignDocument,
    DocumentType,
)
from launchpilot.knowledge.elasticsearch import (
    ElasticsearchCampaignDocumentSearch,
)
from launchpilot.knowledge.postgres import (
    PostgresCampaignDocumentRepository,
)
from launchpilot.knowledge.service import TextRetrievalService
from launchpilot.persistence.postgres import PostgresDatabase
from launchpilot.shared import DateRange


def test_bm25_search_is_campaign_scoped_and_resolves_postgres_source(
    postgres_database: PostgresDatabase,
    elasticsearch_test_index: tuple[str, str],
) -> None:
    workspace_id, campaign_id = _campaign(postgres_database)
    repository = PostgresCampaignDocumentRepository(postgres_database)
    url, index = elasticsearch_test_index
    service = TextRetrievalService(
        repository, ElasticsearchCampaignDocumentSearch(url, index)
    )
    fatigue = service.add(
        CampaignDocument(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            document_type=DocumentType.MEMO,
            title="Meta 소재 피로 메모",
            content="7월 17일부터 소재 피로로 CTR과 구매율이 하락했다.",
            source_ref="memo:creative-fatigue",
        )
    )
    service.add(
        CampaignDocument(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            document_type=DocumentType.BRIEF,
            title="예산 운영 브리프",
            content="검색 광고 예산을 단계적으로 확대한다.",
            source_ref="brief:budget",
        )
    )

    hits = service.search(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        query="소재 피로 CTR 하락",
    )
    hidden = service.search(
        workspace_id=uuid4(),
        campaign_id=campaign_id,
        query="소재 피로",
    )
    resolved = service.resolve(
        document_id=hits[0].document_id,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
    )

    assert hits[0].document_id == fatigue.id
    assert hits[0].campaign_id == campaign_id
    assert hits[0].chunk_id is None
    assert hits[0].rank == 1
    assert hits[0].retrieval_method == "bm25"
    assert hits[0].index_version == index
    assert hits[0].chunker_version == "whole-document-v1"
    assert hits[0].retriever_version == "bm25-v1"
    assert hits[0].score > 0
    assert hidden == ()
    assert resolved == fatigue


def _campaign(database: PostgresDatabase):
    user_id = uuid4()
    workspace_id = uuid4()
    campaign = Campaign.create(
        workspace_id=workspace_id,
        name="BM25 Campaign",
        goal="Search campaign context",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO users(id, google_subject, email, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)""",
            (user_id, f"subject-{user_id}", f"{user_id}@example.com"),
        )
        connection.execute(
            """INSERT INTO workspaces(id, name, created_at)
            VALUES (%s, 'BM25 Workspace', CURRENT_TIMESTAMP)""",
            (workspace_id,),
        )
        connection.execute(
            """INSERT INTO workspace_memberships(
                workspace_id, user_id, role, created_at
            ) VALUES (%s, %s, 'OWNER', CURRENT_TIMESTAMP)""",
            (workspace_id, user_id),
        )
    PostgresCampaignRepository(database).add(campaign)
    return workspace_id, campaign.id
