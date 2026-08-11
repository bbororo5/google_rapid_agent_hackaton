from enum import StrEnum


class PlatformProvider(StrEnum):
    """Stable platform identity shared across connection, binding, and ingestion."""

    YOUTUBE = "YOUTUBE"
    GOOGLE_ADS = "GOOGLE_ADS"
    META_ADS = "META_ADS"
