from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .connectors import AdsConnector


@dataclass(frozen=True, slots=True)
class PlatformAccess:
    provider: str
    access_token: str


class PlatformAccessError(RuntimeError):
    pass


class PlatformAccessUnavailable(PlatformAccessError):
    pass


class PlatformConnectionNotFound(PlatformAccessError):
    pass


class PlatformProviderMismatch(PlatformAccessError):
    pass


class PlatformAuthorizationExpired(PlatformAccessError):
    pass


class PlatformTokenRefreshFailed(PlatformAccessError):
    pass


class PlatformTokenUnavailable(PlatformAccessError):
    pass


class UnsupportedAdsProvider(PlatformAccessError):
    pass


class AdsConnectorUnavailable(PlatformAccessError):
    pass


class AccessTokenProvider(Protocol):
    def resolve(
        self,
        *,
        connection_id: str,
        user_id: str,
        allowed_providers: frozenset[str],
    ) -> PlatformAccess: ...


class AdsConnectorProvider(Protocol):
    def create(self, provider: str) -> AdsConnector: ...
