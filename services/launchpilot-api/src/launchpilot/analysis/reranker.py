from __future__ import annotations

import re
from datetime import datetime
from typing import Sequence
from langchain_core.language_models import BaseChatModel
from launchpilot.knowledge.contracts.retrieval import TextSearchHit


class MarketingDomainReranker:
    """Quality-First LLM Listwise Domain Reranker (RankGPT Architecture).
    Deeply analyzes temporal alignment, marketing concepts, and operational intent without heuristic keyword bias.
    """

    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model

    def rerank(
        self,
        query: str,
        hits: Sequence[TextSearchHit],
        reference_now: datetime | None = None,
    ) -> tuple[TextSearchHit, ...]:
        if not hits or len(hits) <= 1:
            return tuple(hits)

        if not self._model:
            from launchpilot.bootstrap.wiring import agent_model
            self._model = agent_model()

        hit_map = {}
        candidates_text = []
        for idx, h in enumerate(hits, 1):
            hit_map[idx] = h
            doc_type = h.document_type.value if hasattr(h.document_type, "value") else str(h.document_type)
            candidates_text.append(f"[{idx}] 제목: {h.title} (유형: {doc_type}) | 요약: {h.excerpt[:120]}")

        prompt = (
            "당신은 마케팅 도메인 정밀 리랭커(Listwise Reranker)입니다. "
            "사용자 질문의 요구사항(시점, 조치 대상, 질문 의도)과 가장 직접적으로 일치하는 순서대로 후보 번호들을 쉼표로 구분하여 정렬하십시오.\n"
            "일반적인 기획서보다 질문의 특정 시점(주차)이나 조치와 직접 일치하는 문서를 우선 정렬하십시오.\n\n"
            f"[사용자 질문]: {query}\n\n"
            f"[후보 문서 목록]:\n" + "\n".join(candidates_text) + "\n\n"
            "정답 순위 번호 목록만 쉼표로 출력 (예: 3, 1, 2, 4):"
        )

        try:
            res = self._model.invoke(prompt)
            content = res.content if hasattr(res, "content") else str(res)
            ordered_indices = [int(x) for x in re.findall(r"\b\d+\b", content) if int(x) in hit_map]
            
            # Append missing indices
            for idx in hit_map:
                if idx not in ordered_indices:
                    ordered_indices.append(idx)

            reranked = tuple(
                hit_map[idx].model_copy(update={"rank": new_rank})
                for new_rank, idx in enumerate(ordered_indices, 1)
            )
            return reranked
        except Exception:
            return tuple(hits)
