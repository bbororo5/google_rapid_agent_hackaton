from __future__ import annotations

from uuid import UUID

from launchpilot.persistence.postgres import PostgresDatabase

from .contracts.retrieval import CampaignDocument, DocumentType


class PostgresCampaignDocumentRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def add(self, document: CampaignDocument) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO campaign_documents(
                    id, campaign_id, workspace_id, document_type, title, content,
                    source_ref, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    document.id,
                    document.campaign_id,
                    document.workspace_id,
                    document.document_type.value,
                    document.title,
                    document.content,
                    document.source_ref,
                    document.created_at,
                ),
            )

    def get_scoped(
        self, *, document_id: UUID, workspace_id: UUID, campaign_id: UUID
    ) -> CampaignDocument | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM campaign_documents
                WHERE id = %s AND workspace_id = %s AND campaign_id = %s""",
                (document_id, workspace_id, campaign_id),
            ).fetchone()
        if row is None:
            return None
        return CampaignDocument(
            id=row["id"],
            campaign_id=row["campaign_id"],
            workspace_id=row["workspace_id"],
            document_type=DocumentType(row["document_type"]),
            title=row["title"],
            content=row["content"],
            source_ref=row["source_ref"],
            created_at=row["created_at"],
        )

    def list_scoped(
        self, *, workspace_id: UUID, campaign_id: UUID
    ) -> tuple[CampaignDocument, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM campaign_documents
                WHERE workspace_id = %s AND campaign_id = %s
                ORDER BY created_at""",
                (workspace_id, campaign_id),
            ).fetchall()
        return tuple(
            CampaignDocument(
                id=row["id"],
                campaign_id=row["campaign_id"],
                workspace_id=row["workspace_id"],
                document_type=DocumentType(row["document_type"]),
                title=row["title"],
                content=row["content"],
                source_ref=row["source_ref"],
                created_at=row["created_at"],
            )
            for row in rows
        )
