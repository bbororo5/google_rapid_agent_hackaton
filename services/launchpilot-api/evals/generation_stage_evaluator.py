import re
import sqlite3
from uuid import UUID
from dataclasses import dataclass
from typing import Sequence, Any

@dataclass(frozen=True, slots=True)
class GenerationEvaluationResult:
    case_id: str
    query: str
    is_negative: bool
    numeric_exactness: bool
    causal_triad_level: int  # 0, 1, 2
    citation_valid: bool
    valid_citations_count: int
    abstention_passed: bool
    faithfulness_passed: bool
    latency_ms: float
    details: dict[str, Any]

class GenerationStageEvaluator:
    """Official 4-Metric Generation Stage Evaluator for LaunchPilot Agentic RAG.
    1. Deterministic Numeric Exactness (100% exact numerical match)
    2. 3-Hop Causal Triad Synthesis (Level 0, 1, 2)
    3. Real UUID Citation & Provenance Integrity (DB verification)
    4. Calibrated Negative Abstention
    """

    def __init__(self, db_conn: sqlite3.Connection | None = None) -> None:
        self.conn = db_conn

    def evaluate_case(
        self,
        case_id: str,
        query: str,
        is_negative: bool,
        answer_text: str,
        expected_metrics: list[str] | None = None,
        latency_ms: float = 0.0,
    ) -> GenerationEvaluationResult:
        details = {}
        ans = answer_text.strip()
        ans_lower = ans.lower()

        # 1. Negative Abstention
        if is_negative:
            abstain_phrases = ["기록이 없", "찾을 수 없", "존재하지 않", "집행된 적 없", "확인되지 않", "일치하는 정보가 없"]
            abstention_passed = any(p in ans for p in abstain_phrases) and len(ans) > 5
            return GenerationEvaluationResult(
                case_id=case_id,
                query=query,
                is_negative=True,
                numeric_exactness=True,
                causal_triad_level=2 if abstention_passed else 0,
                citation_valid=True,
                valid_citations_count=0,
                abstention_passed=abstention_passed,
                faithfulness_passed=abstention_passed,
                latency_ms=latency_ms,
                details={"abstention_phrases_found": [p for p in abstain_phrases if p in ans]},
            )

        # 2. Deterministic Numeric Exactness
        numeric_passed = True
        if expected_metrics:
            for em in expected_metrics:
                if em.lower() not in ans_lower:
                    numeric_passed = False
                    break
        details["numeric_passed"] = numeric_passed

        # 3. Provenance & Real UUID Citation
        # Format regex: [surface | UUID | timestamp] or [UUID] or (UUID)
        uuid_regex = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
        found_uuids = uuid_regex.findall(ans)
        citation_valid = True
        valid_count = 0
        if self.conn and found_uuids:
            c = self.conn.cursor()
            for u in set(found_uuids):
                r = c.execute("SELECT id FROM campaign_documents WHERE id = ?", (u,)).fetchone()
                if r:
                    valid_count += 1
                else:
                    # Phantom UUID detected!
                    citation_valid = False
        details["found_uuids"] = found_uuids
        details["valid_uuid_count"] = valid_count

        # 4. 3-Hop Causal Triad Synthesis Scoring (Level 0, 1, 2)
        # Hop 1 (Trigger): 지표 이상치, 소진율 과다, 소재 피로, CPA 상승
        # Hop 2 (Action): 삭감, 교체, 변경, 긴급 조치, B안, C안
        # Hop 3 (Retrospective Outcome): ROAS 반등, 안정화, 회고, 성과 개선
        hop1_signals = ["소진", "피로", "cpa", "급증", "이상", "과다", "클릭률 급락", "지표"]
        hop2_signals = ["삭감", "교체", "변경", "조치", "b안", "c안", "수정", "개입"]
        hop3_signals = ["반등", "roas", "안정화", "회고", "개선", "성과", "평가"]

        has_hop1 = any(s in ans_lower for s in hop1_signals)
        has_hop2 = any(s in ans_lower for s in hop2_signals)
        has_hop3 = any(s in ans_lower for s in hop3_signals)

        hop_count = sum([has_hop1, has_hop2, has_hop3])
        if hop_count == 3:
            causal_level = 2 # Complete 3-Hop Triad
        elif hop_count == 2:
            causal_level = 1 # Partial
        else:
            causal_level = 0 # Disconnected Fact

        details["causal_hops"] = {"trigger": has_hop1, "action": has_hop2, "outcome": has_hop3}

        faithfulness_passed = (causal_level >= 1) and numeric_passed

        return GenerationEvaluationResult(
            case_id=case_id,
            query=query,
            is_negative=False,
            numeric_exactness=numeric_passed,
            causal_triad_level=causal_level,
            citation_valid=citation_valid,
            valid_citations_count=valid_count,
            abstention_passed=True,
            faithfulness_passed=faithfulness_passed,
            latency_ms=latency_ms,
            details=details,
        )

    def summarize(self, results: list[GenerationEvaluationResult]) -> dict[str, Any]:
        if not results:
            return {}
        N = len(results)
        pos_results = [r for r in results if not r.is_negative]
        neg_results = [r for r in results if r.is_negative]

        return {
            "total_evaluated_queries": N,
            "numeric_exactness_rate": sum(1 for r in pos_results if r.numeric_exactness) / max(len(pos_results), 1),
            "causal_triad_completion_rate": sum(1 for r in pos_results if r.causal_triad_level == 2) / max(len(pos_results), 1),
            "provenance_citation_validity_rate": sum(1 for r in pos_results if r.citation_valid) / max(len(pos_results), 1),
            "negative_abstention_rate": sum(1 for r in neg_results if r.abstention_passed) / max(len(neg_results), 1),
            "overall_faithfulness_rate": sum(1 for r in results if r.faithfulness_passed) / N,
        }
