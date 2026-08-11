from dataclasses import dataclass
from datetime import UTC, date, datetime

from .errors import DomainError


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise DomainError("period start must be on or before end")
