from __future__ import annotations

from launchpilot.application.ingestion import (
    AdsConnectorUnavailable,
    UnsupportedAdsProvider,
)
from launchpilot.application.ports import AdsConnector
from launchpilot.bootstrap.config import Settings

from .google_ads import GoogleAdsConnector
from .meta_ads import MetaAdsConnector


class AdsConnectorFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self, provider: str) -> AdsConnector:
        if provider == "GOOGLE_ADS":
            try:
                return self._google_ads()
            except RuntimeError as error:
                raise AdsConnectorUnavailable(str(error)) from error
        if provider == "META_ADS":
            return self._meta_ads()
        raise UnsupportedAdsProvider("connection does not expose advertising campaigns")

    def _google_ads(self) -> GoogleAdsConnector:
        mock_url = self._settings.platform_mock_base_url
        return GoogleAdsConnector(
            developer_token=(
                "mock-developer-token"
                if mock_url
                else self._settings.require_google_ads()
            ),
            api_version=self._settings.google_ads_api_version,
            base_url=(
                f"{mock_url}/google" if mock_url else "https://googleads.googleapis.com"
            ),
        )

    def _meta_ads(self) -> MetaAdsConnector:
        mock_url = self._settings.platform_mock_base_url
        return MetaAdsConnector(
            api_version=self._settings.meta_graph_api_version,
            primary_conversion_action=self._settings.meta_primary_conversion_action,
            base_url=(f"{mock_url}/meta" if mock_url else "https://graph.facebook.com"),
        )
