from __future__ import annotations

from launchpilot.evaluation.experiments.contracts import EvaluationCase, GoldEvidence
from launchpilot.evaluation.experiments.perturbation import (
    PerturbationLevel,
    create_naturalized_cases,
    naturalize_case_query,
)


def test_perturbation_levels_transform_queries() -> None:
    evidence = (GoldEvidence(document_ref="doc-001", relevance=3),)
    case = EvaluationCase(
        case_id="case-1",
        query="C0010 캠페인의 소재 피로 진단 근거를 분석 문서에서 찾아줘",
        query_profile="semantic",
        split="tune",
        campaign_ref="C0010",
        evidence=evidence,
    )

    clean = naturalize_case_query(case, PerturbationLevel.CLEAN)
    assert clean == "C0010 캠페인의 소재 피로 진단 근거를 분석 문서에서 찾아줘"

    colloquial = naturalize_case_query(case, PerturbationLevel.COLLOQUIAL_SYNONYM)
    assert "피로도" in colloquial

    jargon = naturalize_case_query(case, PerturbationLevel.MARKETER_JARGON)
    assert "C0010" not in jargon

    all_cases = create_naturalized_cases([case], PerturbationLevel.MARKETER_JARGON)
    assert len(all_cases) == 1
    assert all_cases[0].taxonomy["perturbation_level"] == "marketer_jargon"
