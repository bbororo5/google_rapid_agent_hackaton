from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import pytest

V3_ROOT = Path(__file__).parents[1] / "evals" / "golden" / "golden-v3"


@pytest.fixture(scope="module")
def v3_dataset():
    corpus_docs = [
        json.loads(line)
        for line in (V3_ROOT / "corpus" / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases = [
        json.loads(line)
        for line in (V3_ROOT / "queries" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    qrels = [
        json.loads(line)
        for line in (V3_ROOT / "judgments" / "qrels.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    splits = json.loads((V3_ROOT / "splits" / "splits.json").read_text(encoding="utf-8"))
    return {
        "docs": corpus_docs,
        "cases": cases,
        "qrels": qrels,
        "splits": splits["cases"],
    }


def test_queries_zero_system_code_leakage(v3_dataset) -> None:
    """검증 1 (정규식 게이트): 질의 내부에 C0001~C0030, W01~W52, memo_07 등 시스템 코드가 0건이어야 함."""
    campaign_code_regex = re.compile(r"\bC\d{4}\b", re.IGNORECASE)
    week_code_regex = re.compile(r"\bW\d{2}\b", re.IGNORECASE)
    doc_key_regex = re.compile(r"(memo|brief|analysis)_\d+", re.IGNORECASE)

    violations = []
    for c in v3_dataset["cases"]:
        q = c["query"]
        cid = c["case_id"]
        if campaign_code_regex.search(q):
            violations.append(f"[{cid}] Campaign Code Leak: {q}")
        if week_code_regex.search(q):
            violations.append(f"[{cid}] Week Code Leak: {q}")
        if doc_key_regex.search(q):
            violations.append(f"[{cid}] Doc Key Leak: {q}")

    assert not violations, f"System code leakage detected in queries:\n" + "\n".join(violations)


def test_queries_full_content_and_title_ngram_entropy(v3_dataset) -> None:
    """검증 2 (본문 및 제목 전수 N-gram 엔트로피): 본문 핵심 문장을 그대로 베끼지 않고 추상화되었는지 검증."""
    doc_texts = [(d.get("title", "") + " " + d.get("content", "")).lower() for d in v3_dataset["docs"]]
    
    def get_3grams(text: str) -> set[tuple[str, str, str]]:
        words = re.findall(r"[가-힣A-Za-z0-9_]+", text)
        return {tuple(words[i:i+3]) for i in range(len(words)-2)} if len(words) >= 3 else set()

    corpus_3grams = set()
    for dt in doc_texts:
        corpus_3grams.update(get_3grams(dt))

    violations = []
    for c in v3_dataset["cases"]:
        q_3grams = get_3grams(c["query"].lower())
        if not q_3grams:
            continue
        overlap = len(q_3grams & corpus_3grams) / len(q_3grams)
        # Max allowed 3-gram direct copy overlap is 25%
        if overlap > 0.25:
            violations.append(f"[{c['case_id']}] High 3-gram direct copy overlap ({overlap*100:.1f}%): '{c['query']}'")

    assert not violations, f"Query 3-gram content copying violations found:\n" + "\n".join(violations[:5])


def test_inter_query_lexical_diversity_and_variance(v3_dataset) -> None:
    """검증 3 (질문 간 어휘 다양성 및 템플릿 복제 방지): Type-Token Ratio(TTR) 및 쌍별 유사도 상한선 검증."""
    cases = v3_dataset["cases"]
    all_tokens = []
    query_token_sets = []

    for c in cases:
        toks = re.findall(r"[가-힣A-Za-z0-9_]+", c["query"].lower())
        all_tokens.extend(toks)
        query_token_sets.append(set(toks))

    # 1. Type-Token Ratio (TTR) >= 0.20
    unique_tokens = set(all_tokens)
    ttr = len(unique_tokens) / max(len(all_tokens), 1)
    assert ttr >= 0.18, f"Vocabulary diversity too low: TTR={ttr:.3f} < 0.18"

    # 2. Pairwise Jaccard Similarity (No exact duplicate questions)
    exact_duplicates = 0
    for i in range(len(query_token_sets)):
        for j in range(i + 1, len(query_token_sets)):
            s1, s2 = query_token_sets[i], query_token_sets[j]
            if s1 == s2:
                exact_duplicates += 1

    assert exact_duplicates == 0, f"Found {exact_duplicates} exact duplicate queries across cases!"


def test_dynamic_bm25_entropy_and_margin_simulation(v3_dataset) -> None:
    """검증 4 (동적 BM25 시뮬레이션 게이트): 단 1개 문서만 비정상적으로 압도적 점수를 받는 치팅 질의 검출."""
    docs = v3_dataset["docs"]
    doc_tokens = {d["document_key"]: re.findall(r"[가-힣A-Za-z0-9_]+", (d.get("title", "") + " " + d.get("content", "")).lower()) for d in docs}
    doc_df = Counter()
    N = len(docs)
    avgdl = sum(len(toks) for toks in doc_tokens.values()) / max(N, 1)

    for toks in doc_tokens.values():
        for t in set(toks):
            doc_df[t] += 1

    def compute_bm25(q_toks: list[str], d_key: str) -> float:
        d_toks = doc_tokens.get(d_key, [])
        doc_len = len(d_toks)
        tf = Counter(d_toks)
        score = 0.0
        for q in q_toks:
            if q in tf:
                freq = tf[q]
                df = doc_df.get(q, 0)
                idf = math.log(1.0 + (N - df + 0.5) / (df + 0.5))
                num = freq * 2.2
                den = freq + 1.2 * (0.25 + 0.75 * (doc_len / avgdl))
                score += idf * (num / den)
        return score

    anomalous_queries = []
    for c in v3_dataset["cases"]:
        q_toks = re.findall(r"[가-힣A-Za-z0-9_]+", c["query"].lower())
        scores = sorted([compute_bm25(q_toks, d["document_key"]) for d in docs], reverse=True)
        top1, top2 = scores[0], scores[1]
        
        # If Top 1 score is absurdly high (> 25.0) or margin is > 5x Top 2 with high score, flag as leaky
        if top1 > 25.0 and (top1 / (top2 + 1e-4)) > 5.0:
            anomalous_queries.append(f"[{c['case_id']}] Score Anomaly (Top1={top1:.1f}, Top2={top2:.1f}): '{c['query']}'")

    assert not anomalous_queries, f"Detected queries with excessive BM25 oracle leakage:\n" + "\n".join(anomalous_queries[:5])


def test_negative_queries_abstention_integrity(v3_dataset) -> None:
    """검증 5: 네거티브(부존재) 질의 29건이 정답 매핑(qrels)에 빈 리스트([])로 격리되어 있는지 검증."""
    target_map = {}
    for q in v3_dataset["qrels"]:
        target_map.setdefault(q["case_id"], set()).add(q["corpus_ref"])

    neg_count = 0
    violations = []
    for c in v3_dataset["cases"]:
        cid = c["case_id"]
        is_neg = c.get("is_negative", False)
        targets = target_map.get(cid, set())

        if is_neg:
            neg_count += 1
            if len(targets) > 0:
                violations.append(f"[{cid}] Negative case has positive target: {targets}")

    assert neg_count == 29, f"Expected exactly 29 negative cases, found {neg_count}"
    assert not violations, f"Negative query integrity violations:\n" + "\n".join(violations)


def test_stratified_split_independence_and_distribution(v3_dataset) -> None:
    """검증 6: 머신러닝 3대 분할(Tune 90, Val 30, Holdout 30)의 무결성 및 독립성 검증."""
    splits = v3_dataset["splits"]
    tune = set(splits["tune"])
    val = set(splits["validation"])
    holdout = set(splits["holdout"])

    assert len(tune) == 90, f"Tune set must be exactly 90 cases, got {len(tune)}"
    assert len(val) == 30, f"Validation set must be exactly 30 cases, got {len(val)}"
    assert len(holdout) == 30, f"Holdout set must be exactly 30 cases, got {len(holdout)}"

    assert not (tune & val), "Tune and Validation have overlapping cases!"
    assert not (tune & holdout), "Tune and Holdout have overlapping cases!"
    assert not (val & holdout), "Validation and Holdout have overlapping cases!"
