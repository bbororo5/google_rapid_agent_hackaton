from uuid import uuid4

from launchpilot.campaigns.public import ExternalCampaignBinding
from launchpilot.identity.access_tokens import PlatformAccessTokenProvider
from launchpilot.identity.postgres import PlatformConnection
from launchpilot.performance.ingestion import (
    AdsIngestionSourcePlanner,
    PlatformAccess,
    PlatformAuthorizationExpired,
)
from launchpilot.shared import PlatformProvider


class AccessTokensStub:
    def resolve(
        self,
        *,
        connection_id: str,
        user_id: str,
        allowed_providers: frozenset[str],
    ) -> PlatformAccess:
        if connection_id == "expired":
            raise PlatformAuthorizationExpired("authorization expired")
        assert user_id == "user-1"
        assert allowed_providers == frozenset({"GOOGLE_ADS", "META_ADS"})
        return PlatformAccess(provider=connection_id, access_token="access-token")


class ConnectorFactoryStub:
    def create(self, provider: str):
        return ConnectorStub(PlatformProvider(provider))


class ConnectorStub:
    def __init__(self, provider: PlatformProvider) -> None:
        self.provider = provider

    def list_accounts(self, *, access_token: str):
        return ()

    def list_campaigns(self, *, access_token: str, account_ref: str):
        return ()

    def fetch_campaign_metrics(self, *, access_token: str, request):
        raise NotImplementedError


def binding(provider: PlatformProvider, connection_id: str) -> ExternalCampaignBinding:
    return ExternalCampaignBinding.create(
        campaign_id=uuid4(),
        connection_id=connection_id,
        provider=provider,
        external_account_ref="account",
        external_campaign_ref="campaign",
        display_name="Campaign",
    )


def test_source_planner_builds_available_sources_and_isolates_failure() -> None:
    planner = AdsIngestionSourcePlanner(AccessTokensStub(), ConnectorFactoryStub())

    plan = planner.plan(
        user_id="user-1",
        bindings=(
            binding(PlatformProvider.GOOGLE_ADS, "GOOGLE_ADS"),
            binding(PlatformProvider.META_ADS, "expired"),
        ),
    )

    assert len(plan.sources) == 1
    assert plan.sources[0].connector.provider == PlatformProvider.GOOGLE_ADS
    assert plan.sources[0].access_token == "access-token"
    assert plan.failures == ("META_ADS: authorization expired",)


class ConnectionStoreStub:
    def __init__(self, token: dict[str, object]) -> None:
        self.token = token
        self.saved_token: dict[str, object] | None = None

    def get_connection_token(self, *, connection_id: str, user_id: str):
        return (
            PlatformConnection(
                id=connection_id,
                user_id=user_id,
                provider="GOOGLE_ADS",
                account_ref="customers/1",
                granted_scopes=("adwords",),
            ),
            self.token,
        )

    def upsert_connection(self, **values):
        self.saved_token = values["token"]


class GoogleOAuthStub:
    @staticmethod
    def access_token_expired(token: dict[str, object]) -> bool:
        return True

    @staticmethod
    def refresh_access_token(refresh_token: str) -> dict[str, object]:
        assert refresh_token == "refresh-token"
        return {"access_token": "fresh-token"}


def test_access_token_provider_refreshes_before_returning_access() -> None:
    store = ConnectionStoreStub(
        {"access_token": "old-token", "refresh_token": "refresh-token"}
    )
    provider = PlatformAccessTokenProvider(store, GoogleOAuthStub())  # type: ignore[arg-type]

    access = provider.resolve(
        connection_id="connection-1",
        user_id="user-1",
        allowed_providers=frozenset({"GOOGLE_ADS"}),
    )

    assert access == PlatformAccess(provider="GOOGLE_ADS", access_token="fresh-token")
    assert store.saved_token == {"access_token": "fresh-token"}
