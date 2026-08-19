from __future__ import annotations

import re
from enum import StrEnum
from typing import Sequence
from pydantic import BaseModel, Field
from .contracts import EvaluationCase

class PerturbationLevel(StrEnum):
    CLEAN = "clean"
    COLLOQUIAL_SYNONYM = "colloquial_synonym"
    ENTITY_ALIAS = "entity_alias"
    MARKETER_JARGON = "marketer_jargon"

_SYNONYM_REPLACEMENTS = [
    (r"소재 피로 진단 근거를 분석 문서에서 찾아줘", "크리에이티브 피로도 쌓인 거 분석 리포트에서 찾아줘"),
    (r"소재 피로 진단 근거", "소재 피로도 원인 분석"),
    (r"목표 대비 집행 페이싱과 예산 조치 권고를 기획서와 메모에서 찾아줘", "예산 소진 페이싱이랑 증감액 추천 기획서에서 확인해줘"),
    (r"목표 대비 집행 페이싱", "예산 페이싱 현황"),
    (r"예산 조치 권고", "예산 조정 추천 조치"),
    (r"광고비 지출과 전환 성과를 종합하여", "태운 광고비랑 전환 성과 합쳐서"),
    (r"다음 분기 권고사항을 정리해줘", "다음 분기 액션플랜 정리해줘"),
    (r"광고비를 알려줘", "태운 돈 얼마야?"),
    (r"광고비", "지출 비용"),
    (r"성과를 알려줘", "효율 어땠는지 뽑아줘"),
    (r"원인이 무엇인지", "왜 털렸는지"),
    (r"알려줘", "알려줘"),
]

_JARGON_REPLACEMENTS = [
    (r"Google Ads|google ads|구글 애즈", "구애즈"),
    (r"Meta Ads|meta ads|메타 애즈", "메타"),
    (r"YouTube|youtube", "유튭"),
    (r"전환단가|전환당 비용|CPA", "단가"),
    (r"광고수익률|ROAS", "로아스"),
    (r"클릭률|CTR", "클릭률"),
    (r"소재 피로", "소재 털림"),
    (r"하락|감소", "꺾임"),
    (r"상승|증가", "떡상"),
]

def naturalize_case_query(case: EvaluationCase, level: PerturbationLevel) -> str:
    query = case.query
    if level == PerturbationLevel.CLEAN:
        return query

    # Level 1: Colloquial synonym
    for pattern, repl in _SYNONYM_REPLACEMENTS:
        query = re.sub(pattern, repl, query, flags=re.IGNORECASE)

    if level == PerturbationLevel.COLLOQUIAL_SYNONYM:
        return query

    # Level 2: Entity alias (remove explicit code like C0010 if campaign_name or brand exists)
    if level in (PerturbationLevel.ENTITY_ALIAS, PerturbationLevel.MARKETER_JARGON):
        # Replace explicit campaign code C\d{4} with alias expression
        code_match = re.search(r"\b(C\d{4})\b", query)
        if code_match and case.campaign_ref:
            # Replace code with conversational reference
            query = re.sub(r"\bC\d{4}\b\s*(?:캠페인의?)?", "해당 캠페인 ", query).strip()

    if level == PerturbationLevel.MARKETER_JARGON:
        for pattern, repl in _JARGON_REPLACEMENTS:
            query = re.sub(pattern, repl, query, flags=re.IGNORECASE)

    return " ".join(query.split())


def create_naturalized_cases(
    cases: Sequence[EvaluationCase],
    level: PerturbationLevel,
) -> tuple[EvaluationCase, ...]:
    output = []
    for c in cases:
        new_query = naturalize_case_query(c, level)
        output.append(
            EvaluationCase(
                case_id=f"{c.case_id}.{level.value}",
                query=new_query,
                query_profile=c.query_profile,
                split=c.split,
                campaign_ref=c.campaign_ref if level != PerturbationLevel.MARKETER_JARGON else None,
                evidence=c.evidence,
                taxonomy={**c.taxonomy, "perturbation_level": level.value},
            )
        )
    return tuple(output)
