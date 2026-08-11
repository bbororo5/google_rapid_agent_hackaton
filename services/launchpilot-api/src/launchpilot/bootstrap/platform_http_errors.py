from fastapi import HTTPException, status

from launchpilot.performance.contracts.access import (
    AdsConnectorUnavailable,
    PlatformAccessError,
    PlatformAccessUnavailable,
    PlatformAuthorizationExpired,
    PlatformConnectionNotFound,
    PlatformProviderMismatch,
    PlatformTokenRefreshFailed,
    PlatformTokenUnavailable,
    UnsupportedAdsProvider,
)


def platform_access_http_error(error: PlatformAccessError) -> HTTPException:
    """Translate application errors at the HTTP adapter boundary."""

    if isinstance(error, PlatformConnectionNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, PlatformAuthorizationExpired):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)
        )
    if isinstance(error, PlatformTokenRefreshFailed):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
    if isinstance(error, (PlatformAccessUnavailable, AdsConnectorUnavailable)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        )
    if isinstance(
        error,
        (PlatformProviderMismatch, PlatformTokenUnavailable, UnsupportedAdsProvider),
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
    )
