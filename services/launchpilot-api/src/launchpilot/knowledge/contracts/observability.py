from contextlib import AbstractContextManager
from typing import Protocol

from .search_profile import RetrievalProfile


class RetrievalSearchObservation(Protocol):
    def returned(self, count: int) -> None: ...


class RetrievalObserver(Protocol):
    def observe_search(
        self,
        *,
        profile: RetrievalProfile,
        query_length: int,
        document_type_filter_count: int,
        top_k: int,
    ) -> AbstractContextManager[RetrievalSearchObservation]: ...
