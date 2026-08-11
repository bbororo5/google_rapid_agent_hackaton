"""Small shared kernel for cross-module value types and errors."""

from .errors import DomainError, NotFoundError
from .platforms import PlatformProvider
from .time import DateRange, utc_now

__all__ = [
    "DateRange",
    "DomainError",
    "NotFoundError",
    "PlatformProvider",
    "utc_now",
]
