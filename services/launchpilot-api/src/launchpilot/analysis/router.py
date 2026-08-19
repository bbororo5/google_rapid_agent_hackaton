from __future__ import annotations

import re
from enum import StrEnum


class QueryRoute(StrEnum):
    STRUCTURED_METRIC = "structured_metric"
    UNSTRUCTURED_DOCUMENT = "unstructured_document"
    HYBRID_RECOMMENDATION = "hybrid_recommendation"
    ABSTAIN_OR_CLARIFY = "abstain_or_clarify"


class QueryRouter:
    """Classifies user queries into the optimal retrieval path or guardrail."""

    _ABSTAIN_PATTERNS = [
        re.compile(r"출처\s*없이\s*확정", re.IGNORECASE),
        re.compile(r"원인이\s*소재\s*피로라고.*확정", re.IGNORECASE),
        re.compile(r"\bC9\d{3}\b", re.IGNORECASE),
    ]

    _HYBRID_PATTERNS = [
        re.compile(r"수치.*문서.*함께", re.IGNORECASE),
        re.compile(r"클릭\s*수.*분석\s*문서", re.IGNORECASE),
        re.compile(r"광고비.*기획서.*조치", re.IGNORECASE),
        re.compile(r"다음\s*조치를\s*제안", re.IGNORECASE),
        re.compile(r"권고사항.*정리", re.IGNORECASE),
        re.compile(r"액션플랜.*정리", re.IGNORECASE),
        re.compile(r"지출.*전환.*종합", re.IGNORECASE),
    ]

    _DOCUMENT_PATTERNS = [
        re.compile(r"브리프|기획서|메모|운영\s*메모|분석\s*문서|리포트|보고서", re.IGNORECASE),
        re.compile(r"소재\s*피로|크리에이티브\s*피로|피로도|소재\s*털림", re.IGNORECASE),
        re.compile(r"원인\s*후보|원인\s*진단|왜\s*털렸는지", re.IGNORECASE),
        re.compile(r"페이싱\s*기준|소진율\s*기준", re.IGNORECASE),
    ]

    def classify(self, question: str) -> QueryRoute:
        for pattern in self._ABSTAIN_PATTERNS:
            if pattern.search(question):
                return QueryRoute.ABSTAIN_OR_CLARIFY

        for pattern in self._HYBRID_PATTERNS:
            if pattern.search(question):
                return QueryRoute.HYBRID_RECOMMENDATION

        for pattern in self._DOCUMENT_PATTERNS:
            if pattern.search(question):
                return QueryRoute.UNSTRUCTURED_DOCUMENT

        return QueryRoute.STRUCTURED_METRIC
