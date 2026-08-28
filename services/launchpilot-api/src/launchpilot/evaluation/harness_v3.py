from __future__ import annotations

import json
import math
import re
import sqlite3
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

OUT_ROOT = Path("services/launchpilot-api/evals/golden/golden-v3")


@dataclass(frozen=True, slots=True)
class SearchHitResult:
    document_id: str
    document_key: str
    campaign_ref: str
    score: float
    rank: int


@dataclass(frozen=True, slots=True)
class EvaluationMetricSummary:
    total_cases: int
    solvable_cases: int
    negative_cases: int
    recall_at_5: float
    mrr_at_5: float
    precision_at_1: float
    top1_count: int
    negative_correct_abstentions: int
    negative_false_positives: int
    split_metrics: dict[str, dict[str, float]]
    task_metrics: dict[str, dict[str, float]]


class BaseBlackBoxRetriever(ABC):
    """Air-gapped black-box interface for search engines under evaluation."""

    @abstractmethod
    def search(
        self, query: str, active_campaign_anchor: str | None = None, top_k: int = 5
    ) -> Sequence[SearchHitResult]:
        pass


class AirGappedEvaluationHarness:
    """Legacy retrieval-only harness retained for synthetic V3 reproduction.

    It does not represent the task-centric evaluation entry point and must not be used
    for architecture release decisions.
    """

    def __init__(self, golden_root: Path = OUT_ROOT) -> None:
        self._root = golden_root
        self._cases = [
            json.loads(line)
            for line in (golden_root / "queries" / "cases.jsonl").read_text().splitlines()
            if line.strip()
        ]
        self._qrels = [
            json.loads(line)
            for line in (golden_root / "judgments" / "qrels.jsonl").read_text().splitlines()
            if line.strip()
        ]
        self._splits = json.loads((golden_root / "splits" / "splits.json").read_text())

        # Build internal ground truth mapping (invisible to the retriever)
        self._target_map: dict[str, set[str]] = defaultdict(set)
        for q in self._qrels:
            self._target_map[q["case_id"]].add(q["corpus_ref"])

        self._split_map: dict[str, str] = {}
        for s_name, ids in self._splits["cases"].items():
            for cid in ids:
                self._split_map[cid] = s_name

    def run_evaluation(
        self,
        retriever_name: str,
        retriever: BaseBlackBoxRetriever,
        negative_score_threshold: float = 0.0,
    ) -> EvaluationMetricSummary:
        total_cases = len(self._cases)
        solvable_cases = 0
        negative_cases = 0

        hits_at_5 = 0
        rr_sum = 0.0
        top1_count = 0

        neg_correct = 0
        neg_fp = 0

        split_accum = defaultdict(lambda: {"solvable": 0, "hits_5": 0, "rr_sum": 0.0, "top1": 0})
        task_accum = defaultdict(lambda: {"solvable": 0, "hits_5": 0, "rr_sum": 0.0, "top1": 0})

        for case in self._cases:
            case_id = case["case_id"]
            query = case["query"]
            task = case.get("analysis_task", "unknown")
            split_name = self._split_map.get(case_id, "unknown")
            gold_targets = self._target_map.get(case_id, set())

            # Extract user session context (active campaign anchor if mentioned)
            c_code_match = re.search(r"\bC\d{4}\b", query.upper())
            active_anchor = c_code_match.group(0) if c_code_match else None

            # 1. Pure Black-box invocation: feed ONLY query string + anchor
            results = retriever.search(query, active_campaign_anchor=active_anchor, top_k=5)
            retrieved_keys = [r.document_key for r in results]

            if not gold_targets:
                # Negative / Unanswerable query
                negative_cases += 1
                if not results or (results and results[0].score <= negative_score_threshold):
                    neg_correct += 1
                else:
                    neg_fp += 1
            else:
                # Solvable query with gold targets
                solvable_cases += 1
                split_accum[split_name]["solvable"] += 1
                task_accum[task]["solvable"] += 1

                matched_rank = None
                for rank, d_key in enumerate(retrieved_keys[:5], 1):
                    # Check if document key matches gold target
                    if any(d_key in target or target.endswith(f":{d_key}") for target in gold_targets):
                        matched_rank = rank
                        break

                if matched_rank is not None:
                    hits_at_5 += 1
                    rr_sum += 1.0 / matched_rank
                    split_accum[split_name]["hits_5"] += 1
                    split_accum[split_name]["rr_sum"] += 1.0 / matched_rank
                    if matched_rank == 1:
                        top1_count += 1
                        split_accum[split_name]["top1"] += 1
                        task_accum[task]["top1"] += 1

        rec = hits_at_5 / max(solvable_cases, 1)
        mrr = rr_sum / max(solvable_cases, 1)
        prec1 = top1_count / max(solvable_cases, 1)

        split_metrics = {}
        for s_name, data in split_accum.items():
            s_solv = max(data["solvable"], 1)
            split_metrics[s_name] = {
                "solvable_cases": data["solvable"],
                "recall_at_5": round(data["hits_5"] / s_solv, 4),
                "mrr_at_5": round(data["rr_sum"] / s_solv, 4),
                "precision_at_1": round(data["top1"] / s_solv, 4),
                "top1_count": data["top1"],
            }

        task_metrics = {}
        for t_name, data in task_accum.items():
            t_solv = max(data["solvable"], 1)
            task_metrics[t_name] = {
                "solvable_cases": data["solvable"],
                "recall_at_5": round(data["hits_5"] / t_solv, 4),
                "mrr_at_5": round(data["rr_sum"] / t_solv, 4),
                "precision_at_1": round(data["top1"] / t_solv, 4),
                "top1_count": data["top1"],
            }

        return EvaluationMetricSummary(
            total_cases=total_cases,
            solvable_cases=solvable_cases,
            negative_cases=negative_cases,
            recall_at_5=round(rec, 4),
            mrr_at_5=round(mrr, 4),
            precision_at_1=round(prec1, 4),
            top1_count=top1_count,
            negative_correct_abstentions=neg_correct,
            negative_false_positives=neg_fp,
            split_metrics=split_metrics,
            task_metrics=task_metrics,
        )
