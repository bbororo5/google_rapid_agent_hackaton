from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from launchpilot.evaluation.contracts import (
    Answerability,
    EvalSpecification,
    EvidenceAssessment,
    EvidenceJudgment,
    ExpectedBehavior,
    GraderKind,
    InformationModality,
    LexicalNeed,
    PortfolioRole,
    QueryCharacteristics,
    QueryRecord,
    QuerySource,
    RequiredFact,
    ReviewStatus,
    SourceCardinality,
    TaskShape,
)

_NON_ID = re.compile(r"[^a-z0-9]+")


def convert_v2_cases(
    cases: Sequence[Mapping[str, Any]],
    qrels: Sequence[Mapping[str, Any]],
    *,
    case_ids: set[str],
    portfolio: PortfolioRole,
    spec_version: str = "golden-v2-spec-v0",
) -> tuple[tuple[QueryRecord, ...], tuple[EvalSpecification, ...]]:
    qrels_by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for qrel in qrels:
        qrels_by_case[str(qrel["case_id"])].append(qrel)
    selected = sorted(
        (case for case in cases if str(case["case_id"]) in case_ids),
        key=lambda case: str(case["case_id"]),
    )
    selected_ids = {str(case["case_id"]) for case in selected}
    if selected_ids != case_ids:
        raise ValueError(f"unknown selected case ids: {sorted(case_ids - selected_ids)}")
    queries = tuple(_query_record(case, portfolio) for case in selected)
    specs = tuple(
        _eval_specification(case, qrels_by_case[str(case["case_id"])], spec_version)
        for case in selected
    )
    return queries, specs


def write_portfolio_contracts(
    output_root: Path,
    queries: Sequence[QueryRecord],
    specifications: Sequence[EvalSpecification],
) -> None:
    query_ids = [item.query_id for item in queries]
    specification_query_ids = [item.query_id for item in specifications]
    if len(query_ids) != len(set(query_ids)):
        raise ValueError("query ids must be unique")
    if len(specification_query_ids) != len(set(specification_query_ids)):
        raise ValueError("specification query ids must be unique")
    if set(query_ids) != set(specification_query_ids):
        raise ValueError("query and specification ids differ")
    portfolio_roles = {item.portfolio.value for item in queries}
    if len(portfolio_roles) != 1:
        raise ValueError("one contract artifact must contain exactly one portfolio role")
    output_root.mkdir(parents=True, exist_ok=False)
    _write_jsonl(output_root / "queries.jsonl", queries)
    _write_jsonl(output_root / "eval-specifications.jsonl", specifications)
    payload = {
        "contract_schema_version": "architecture-eval-v1",
        "portfolio_role": next(iter(portfolio_roles)),
        "query_count": len(queries),
        "specification_count": len(specifications),
        "query_source_distribution": _counts(item.source.value for item in queries),
        "review_status_distribution": _counts(
            item.review_status.value for item in specifications
        ),
        "spec_version_distribution": _counts(
            item.spec_version for item in specifications
        ),
        "fingerprint": _fingerprint(queries, specifications),
    }
    (output_root / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _query_record(case: Mapping[str, Any], portfolio: PortfolioRole) -> QueryRecord:
    profile = str(case["query_profile"])
    sources = {str(item) for item in case.get("required_sources", ())}
    ambiguity = case.get("ambiguity")
    if isinstance(ambiguity, Mapping):
        missing_source = ambiguity.get("missing_source")
        if isinstance(missing_source, str):
            sources.add(missing_source)
    if sources == {"pg"}:
        modalities = (InformationModality.STRUCTURED,)
    elif sources == {"documents"}:
        modalities = (InformationModality.UNSTRUCTURED,)
    else:
        modalities = (InformationModality.MIXED,)
    if profile == "lexical_identifier":
        lexical_need = LexicalNeed.EXACT
    elif profile in {"semantic", "entity_semantic", "mixed_structured_semantic"}:
        lexical_need = LexicalNeed.PARAPHRASE_GAP
    else:
        lexical_need = LexicalNeed.NONE
    scope_type = str(case.get("scope_type", ""))
    if bool(case.get("unanswerable", False)):
        cardinality = SourceCardinality.UNKNOWN
    elif scope_type in {"cross_campaign_period", "cross_platform_period", "multi_source"}:
        cardinality = SourceCardinality.MULTIPLE
    else:
        cardinality = SourceCardinality.SINGLE
    return QueryRecord(
        query_id=str(case["case_id"]),
        text=str(case["query"]),
        language=str(case.get("language", "ko-KR")),
        source=QuerySource.SYNTHETIC,
        portfolio=portfolio,
        characteristics=QueryCharacteristics(
            modalities=modalities,
            lexical_need=lexical_need,
            entity_centric=(
                profile in {"lexical_identifier", "entity_semantic"}
                or case.get("analysis_task") == "entity_resolution"
            ),
            hop_count=2 if str(case.get("difficulty", "")).startswith("l4_") else 1,
            task_shape=_task_shape(case),
            source_cardinality=cardinality,
            tags=tuple(sorted(str(item) for item in case.get("risk_types", ()))),
        ),
        leakage_group_ids=tuple(
            sorted(str(item) for item in case.get("leakage_group_ids", ()))
        ),
    )


def _eval_specification(
    case: Mapping[str, Any],
    qrels: Sequence[Mapping[str, Any]],
    spec_version: str,
) -> EvalSpecification:
    query_id = str(case["case_id"])
    answerability = _answerability(case)
    facts = tuple(
        RequiredFact(
            fact_id=_fact_id(index, str(item["key"])),
            description=f"Expected fact: {item['key']}",
            grader=(
                GraderKind.DETERMINISTIC
                if case["validation_status"] == "auto_validated"
                else GraderKind.HUMAN
            ),
            expected_values=(str(item["value"]),),
            unit=str(item["unit"]) if item.get("unit") is not None else None,
        )
        for index, item in enumerate(case.get("expected_facts", ()), start=1)
    )
    evidence = tuple(
        EvidenceAssessment(
            evidence_ref=str(qrel["corpus_ref"]),
            judgment=EvidenceJudgment.KNOWN_RELEVANT,
            relevance_grade=int(qrel.get("relevance", 1)),
            rationale=str(qrel["reason"]) if qrel.get("reason") else None,
        )
        for qrel in sorted(qrels, key=lambda item: str(item["corpus_ref"]))
        if int(qrel.get("relevance", 1)) > 0
    )
    return EvalSpecification(
        spec_id=f"{query_id}.spec",
        spec_version=spec_version,
        query_id=query_id,
        answerability=answerability,
        required_facts=facts,
        expected_behaviors=_expected_behaviors(case, answerability),
        evidence_assessments=evidence,
        review_status=ReviewStatus(str(case["validation_status"])),
        grader_rubric_version="golden-v2-derived-v0",
    )


def _answerability(case: Mapping[str, Any]) -> Answerability:
    if bool(case.get("unanswerable", False)) or case.get("answer_mode") == "abstention":
        return Answerability.INSUFFICIENT_EVIDENCE
    if case.get("answer_mode") == "clarification" or case.get("ambiguity"):
        return Answerability.AMBIGUOUS
    return Answerability.ANSWERABLE


def _expected_behaviors(
    case: Mapping[str, Any], answerability: Answerability
) -> tuple[ExpectedBehavior, ...]:
    if answerability == Answerability.AMBIGUOUS:
        return (ExpectedBehavior.CLARIFY,)
    if answerability == Answerability.INSUFFICIENT_EVIDENCE:
        return (ExpectedBehavior.ABSTAIN,)
    if case.get("answer_mode") == "data_quality_alert":
        return (ExpectedBehavior.ANSWER, ExpectedBehavior.WARN)
    return (ExpectedBehavior.ANSWER,)


def _task_shape(case: Mapping[str, Any]) -> TaskShape:
    task = str(case.get("analysis_task", ""))
    if "comparison" in task:
        return TaskShape.COMPARISON
    if task == "aggregation":
        return TaskShape.AGGREGATION
    if task in {"causal_diagnosis", "recommendation", "goal_pacing"}:
        return TaskShape.SYNTHESIS
    return TaskShape.LOOKUP


def _fact_id(index: int, key: str) -> str:
    slug = _NON_ID.sub(".", key.casefold()).strip(".") or "value"
    return f"fact.{index:02d}.{slug}"


def _counts(values: Iterable[str]) -> dict[str, int]:
    output: dict[str, int] = defaultdict(int)
    for value in values:
        output[str(value)] += 1
    return dict(sorted(output.items()))


def _fingerprint(
    queries: Sequence[QueryRecord], specifications: Sequence[EvalSpecification]
) -> str:
    payload = {
        "queries": [item.model_dump(mode="json") for item in queries],
        "specifications": [item.model_dump(mode="json") for item in specifications],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _write_jsonl(
    path: Path, items: Sequence[QueryRecord] | Sequence[EvalSpecification]
) -> None:
    path.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            + "\n"
            for item in items
        ),
        encoding="utf-8",
    )
