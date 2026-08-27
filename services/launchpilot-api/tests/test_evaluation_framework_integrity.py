from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID

import pytest

# Ensure evals package is importable
EVALS_DIR = Path(__file__).parents[1] / "evals"
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parents[1]))

from evals.generation_stage_evaluator import (
    GenerationGroundTruth,
    GenerationStageEvaluator,
)
from evals.retrieval_stage_evaluator import RetrievalStageEvaluator
from launchpilot.knowledge.contracts.retrieval import DocumentType, TextSearchHit

V3_ROOT = Path(__file__).parents[1] / "evals" / "golden" / "golden-v3"


@pytest.fixture(scope="module")
def evaluation_assets():
    corpus_docs = {
        json.loads(line)["id"]: json.loads(line)
        for line in (V3_ROOT / "corpus" / "documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    gen_ground_truths = [
        json.loads(line)
        for line in (V3_ROOT / "judgments" / "generation_ground_truth.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    return {
        "corpus_docs": corpus_docs,
        "gen_ground_truths": gen_ground_truths,
    }


def test_generation_ground_truth_dataset_integrity(evaluation_assets) -> None:
    """1. 생성 정답 데이터셋(150건)의 UUID 실존 여부 및 네거티브 격리 전수 검증."""
    corpus_docs = evaluation_assets["corpus_docs"]
    gts = evaluation_assets["gen_ground_truths"]

    assert len(gts) == 150, (
        f"Expected 150 generation ground truth cases, got {len(gts)}"
    )

    neg_count = 0
    pos_count = 0
    for entry in gts:
        cid = entry["case_id"]
        is_neg = entry["is_negative"]

        if is_neg:
            neg_count += 1
            assert len(entry["expected_document_ids"]) == 0, (
                f"[{cid}] Negative case has document targets!"
            )
            assert len(entry["expected_numbers"]) == 0, (
                f"[{cid}] Negative case has expected numbers!"
            )
        else:
            pos_count += 1
            assert len(entry["expected_document_ids"]) > 0, (
                f"[{cid}] Positive case missing expected document IDs!"
            )
            for doc_id in entry["expected_document_ids"]:
                assert doc_id in corpus_docs, (
                    f"[{cid}] Expected doc ID {doc_id} does not exist in corpus!"
                )
            triad = entry["causal_triad"]
            assert (
                "trigger_anomaly" in triad
                and "action_decision" in triad
                and "retrospective_outcome" in triad
            )

    assert neg_count == 29, f"Expected 29 negative cases, got {neg_count}"
    assert pos_count == 121, f"Expected 121 positive cases, got {pos_count}"


def test_retrieval_evaluator_scoring_logic() -> None:
    """Known-relevant, known-irrelevant, and rank diagnostics are independent."""
    evaluator = RetrievalStageEvaluator(top_k=5)

    target_uuid = "a0c38064-1d17-5bed-97c8-0cd422246a7a"
    distractor_uuid = "11111111-2222-3333-4444-555555555555"

    mock_hits = [
        TextSearchHit(
            document_id=UUID(target_uuid),
            campaign_id=UUID("1e551ee8-0b16-5121-aa1c-a435e0d96105"),
            source_ref="c0001:memo_07",
            title="Target Memo",
            document_type=DocumentType.MEMO,
            excerpt="Target content",
            score=1.0,
            rank=1,
            retrieval_method="bm25",
            index_version="v3",
            chunker_version="v3",
            retriever_version="v3",
        )
    ]

    res = evaluator.evaluate_case(
        case_id="case_001",
        query="Mock Query",
        target_refs={target_uuid},
        retrieved_hits=mock_hits,
        distractor_refs={distractor_uuid},
        latency_ms=120.0,
    )

    assert res.known_relevant_hit is True
    assert res.known_relevant_recall == 1.0
    assert res.reciprocal_rank == 1.0
    assert res.known_irrelevant_rejection_rate == 1.0
    assert res.multihop_coverage is None
    assert res.unjudged_count == 0
    assert res.latency_ms == 120.0


def test_retrieval_evaluator_preserves_unjudged_and_negative_semantics() -> None:
    evaluator = RetrievalStageEvaluator(top_k=5)
    unjudged_hit = TextSearchHit(
        document_id=UUID("aaaaaaaa-2222-3333-4444-555555555555"),
        campaign_id=UUID("1e551ee8-0b16-5121-aa1c-a435e0d96105"),
        source_ref="c0001:memo_unjudged",
        title="Unjudged Memo",
        document_type=DocumentType.MEMO,
        excerpt="Potentially useful content",
        score=1.0,
        rank=1,
        retrieval_method="dense",
        index_version="v3",
        chunker_version="v3",
        retriever_version="v3",
    )

    positive = evaluator.evaluate_case(
        case_id="positive",
        query="query",
        target_refs={"aaaaaaaa-2222-3333-4444-55555555555"},
        retrieved_hits=(unjudged_hit,),
        distractor_refs=set(),
        latency_ms=None,
    )
    assert positive.known_relevant_hit is False
    assert positive.unjudged_count == 1
    assert positive.judged_precision is None
    assert positive.known_irrelevant_rejection_rate is None

    negative = evaluator.evaluate_case(
        case_id="negative",
        query="missing event",
        target_refs=set(),
        retrieved_hits=(unjudged_hit,),
        distractor_refs=set(),
        latency_ms=None,
    )
    assert negative.known_relevant_recall is None
    assert negative.reciprocal_rank is None
    assert negative.negative_retrieval_abstained is False
    assert negative.unjudged_count == 1

    summary = evaluator.summarize([positive, negative])
    assert summary["known_irrelevant_rejection_rate"] is None
    assert summary["negative_retrieval_abstention_rate"] == 0.0
    assert summary["mean_unjudged_at_k"] == 1.0


def test_generation_evaluator_pure_comparator_logic(evaluation_assets) -> None:
    """Legacy V3 lexical proxy remains deterministic and explicitly non-semantic."""
    evaluator = GenerationStageEvaluator()
    gts = evaluation_assets["gen_ground_truths"]

    pos_sample = next(g for g in gts if not g["is_negative"])
    gt_obj = GenerationGroundTruth(
        case_id=pos_sample["case_id"],
        is_negative=False,
        expected_document_ids=tuple(pos_sample["expected_document_ids"]),
        expected_numbers=tuple(pos_sample["expected_numbers"]),
        causal_triad=pos_sample["causal_triad"],
        canonical_gold_answer=pos_sample["canonical_gold_answer"],
    )
    res_gold = evaluator.evaluate_case(pos_sample["canonical_gold_answer"], gt_obj)
    assert res_gold.numeric_exactness is True, "Gold answer failed numeric exactness!"
    assert res_gold.causal_triad_level == 2, (
        "Gold answer failed 3-Hop causal triad completion!"
    )
    assert res_gold.faithfulness_passed is True

    fake_ans = "오로라 리테일 캠페인에서 성과가 아주 좋았고 많은 매출을 달성했습니다."
    res_fake = evaluator.evaluate_case(fake_ans, gt_obj)
    assert res_fake.numeric_exactness is False, (
        "Hallucinated answer unexpectedly passed numeric exactness!"
    )

    neg_sample = next(g for g in gts if g["is_negative"])
    neg_gt_obj = GenerationGroundTruth(
        case_id=neg_sample["case_id"],
        is_negative=True,
        expected_document_ids=(),
        expected_numbers=(),
        causal_triad=neg_sample["causal_triad"],
        canonical_gold_answer=neg_sample["canonical_gold_answer"],
    )
    res_neg_pass = evaluator.evaluate_case(
        "데이터베이스에 해당 채널에 대한 집행 기록이 없습니다.", neg_gt_obj
    )
    assert res_neg_pass.abstention_passed is True
    assert res_neg_pass.faithfulness_passed is True

    res_neg_fail = evaluator.evaluate_case(
        "네, 5월 틱톡 프로모션으로 1억 원의 매출을 달성했습니다.", neg_gt_obj
    )
    assert res_neg_fail.abstention_passed is False
    assert res_neg_fail.faithfulness_passed is False
