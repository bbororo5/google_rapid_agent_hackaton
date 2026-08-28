from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GenerationGroundTruth:
    case_id: str
    is_negative: bool
    expected_document_ids: tuple[str, ...]
    expected_numbers: tuple[str, ...]
    causal_triad: dict[str, str]
    canonical_gold_answer: str


@dataclass(frozen=True, slots=True)
class GenerationEvaluationResult:
    case_id: str
    is_negative: bool
    numeric_exactness: bool
    causal_triad_level: int  # 0, 1, 2
    citation_valid: bool
    citation_precision: float
    citation_recall: float
    abstention_passed: bool
    lexical_proxy_passed: bool
    latency_ms: float
    details: dict[str, Any]

    @property
    def faithfulness_passed(self) -> bool:
        """Deprecated compatibility alias; this result is not faithfulness."""
        return self.lexical_proxy_passed


class GenerationStageEvaluator:
    """Legacy lexical-conformance comparator for the synthetic V3 fixture.

    This class does not establish semantic correctness, causal reasoning, or
    claim-to-evidence faithfulness. Its keyword, number-string, and UUID checks are
    diagnostics only and must not be used as a production quality gate.
    """

    def evaluate_case(
        self,
        answer_text: str,
        ground_truth: GenerationGroundTruth,
        latency_ms: float = 0.0,
    ) -> GenerationEvaluationResult:
        ans = answer_text.strip()
        ans_lower = ans.lower()
        details: dict[str, Any] = {}

        # 1. Negative Abstention Verification
        if ground_truth.is_negative:
            abstain_phrases = [
                "기록이 없",
                "찾을 수 없",
                "존재하지 않",
                "집행된 적 없",
                "확인되지 않",
                "일치하는 정보가 없",
            ]
            abstention_passed = any(p in ans for p in abstain_phrases) and len(ans) > 5
            return GenerationEvaluationResult(
                case_id=ground_truth.case_id,
                is_negative=True,
                numeric_exactness=True,
                causal_triad_level=2 if abstention_passed else 0,
                citation_valid=True,
                citation_precision=1.0,
                citation_recall=1.0,
                abstention_passed=abstention_passed,
                lexical_proxy_passed=abstention_passed,
                latency_ms=latency_ms,
                details={"abstention_passed": abstention_passed},
            )

        # 2. Deterministic Numeric Exactness (against ground_truth.expected_numbers)
        numeric_matches = []
        numeric_passed = True
        for num in ground_truth.expected_numbers:
            matched = num.lower() in ans_lower
            numeric_matches.append(matched)
            if not matched:
                numeric_passed = False
        details["expected_numbers"] = ground_truth.expected_numbers
        details["numeric_matches"] = numeric_matches
        details["numeric_passed"] = numeric_passed

        # 3. Provenance & Expected Citation Matching
        uuid_regex = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            re.IGNORECASE,
        )
        found_uuids = set(uuid_regex.findall(ans))
        expected_uuids = set(ground_truth.expected_document_ids)

        if not expected_uuids:
            citation_precision = 1.0
            citation_recall = 1.0
            citation_valid = True
        else:
            correctly_cited = found_uuids & expected_uuids
            citation_precision = len(correctly_cited) / max(len(found_uuids), 1)
            citation_recall = len(correctly_cited) / len(expected_uuids)
            citation_valid = len(correctly_cited) > 0

        details["found_uuids"] = list(found_uuids)
        details["expected_uuids"] = list(expected_uuids)
        details["citation_precision"] = citation_precision
        details["citation_recall"] = citation_recall

        # 4. 3-Hop Causal Triad Synthesis Scoring (Level 0, 1, 2)
        # Evaluates against ground_truth.causal_triad entities
        triad = ground_truth.causal_triad
        trigger_terms = [
            t
            for t in re.findall(r"[가-힣A-Za-z0-9_]+", triad.get("trigger_anomaly", ""))
            if len(t) >= 2
        ]
        action_terms = [
            t
            for t in re.findall(r"[가-힣A-Za-z0-9_]+", triad.get("action_decision", ""))
            if len(t) >= 2
        ]
        outcome_terms = [
            t
            for t in re.findall(
                r"[가-힣A-Za-z0-9_]+", triad.get("retrospective_outcome", "")
            )
            if len(t) >= 2
        ]

        has_trigger = any(t.lower() in ans_lower for t in trigger_terms)
        has_action = any(t.lower() in ans_lower for t in action_terms)
        has_outcome = any(t.lower() in ans_lower for t in outcome_terms)

        hop_count = sum([has_trigger, has_action, has_outcome])
        if hop_count == 3:
            causal_level = 2
        elif hop_count >= 1:
            causal_level = 1
        else:
            causal_level = 0

        details["causal_components"] = {
            "has_trigger": has_trigger,
            "has_action": has_action,
            "has_outcome": has_outcome,
            "level": causal_level,
        }

        faithfulness_passed = (causal_level >= 1) and numeric_passed

        return GenerationEvaluationResult(
            case_id=ground_truth.case_id,
            is_negative=False,
            numeric_exactness=numeric_passed,
            causal_triad_level=causal_level,
            citation_valid=citation_valid,
            citation_precision=citation_precision,
            citation_recall=citation_recall,
            abstention_passed=True,
            lexical_proxy_passed=faithfulness_passed,
            latency_ms=latency_ms,
            details=details,
        )

    def summarize(
        self, results: Sequence[GenerationEvaluationResult]
    ) -> dict[str, Any]:
        if not results:
            return {}
        N = len(results)
        pos_results = [r for r in results if not r.is_negative]
        neg_results = [r for r in results if r.is_negative]

        return {
            "total_evaluated_queries": N,
            "numeric_exactness_rate": sum(1 for r in pos_results if r.numeric_exactness)
            / max(len(pos_results), 1),
            "causal_triad_completion_rate": sum(
                1 for r in pos_results if r.causal_triad_level == 2
            )
            / max(len(pos_results), 1),
            "citation_precision": sum(r.citation_precision for r in pos_results)
            / max(len(pos_results), 1),
            "citation_recall": sum(r.citation_recall for r in pos_results)
            / max(len(pos_results), 1),
            "negative_abstention_rate": sum(
                1 for r in neg_results if r.abstention_passed
            )
            / max(len(neg_results), 1),
            "overall_lexical_proxy_pass_rate": sum(
                1 for r in results if r.lexical_proxy_passed
            )
            / N,
        }
