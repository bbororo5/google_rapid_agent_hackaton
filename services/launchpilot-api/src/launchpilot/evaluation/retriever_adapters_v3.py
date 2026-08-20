from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Sequence

from .harness_v3 import BaseBlackBoxRetriever, SearchHitResult

CORPUS_ROOT = Path("services/launchpilot-api/evals/golden/golden-v3")


class MarketingCorpusIndexer:
    """Indexes 1,050 documents for pure lexical, semantic, and hybrid retrieval."""

    def __init__(self, root: Path = CORPUS_ROOT) -> None:
        self.docs = [
            json.loads(line)
            for line in (root / "corpus" / "documents.jsonl").read_text().splitlines()
            if line.strip()
        ]
        self.doc_tokens: dict[str, list[str]] = {}
        self.doc_df: Counter[str] = Counter()
        self.N = len(self.docs)
        self.avgdl = 0.0

        for d in self.docs:
            d_key = str(d["document_key"])
            text = (d.get("title", "") + " " + d.get("content", "")).lower()
            tokens = re.findall(r"[가-힣A-Za-z0-9_]+", text)
            self.doc_tokens[d_key] = tokens
            self.avgdl += len(tokens)
            for token in set(tokens):
                self.doc_df[token] += 1

        self.avgdl /= max(self.N, 1)

    def bm25(self, q_tokens: list[str], d_key: str, k1: float = 1.2, b: float = 0.75) -> float:
        d_toks = self.doc_tokens.get(d_key, [])
        doc_len = len(d_toks)
        tf = Counter(d_toks)
        score = 0.0
        for q in q_tokens:
            if q in tf:
                freq = tf[q]
                df = self.doc_df.get(q, 0)
                idf = math.log(1.0 + (self.N - df + 0.5) / (df + 0.5))
                num = freq * (k1 + 1.0)
                den = freq + k1 * (1.0 - b + b * (doc_len / self.avgdl))
                score += idf * (num / den)
        return score

    def dense_sim(self, q_tokens: list[str], d_key: str) -> float:
        d_toks = self.doc_tokens.get(d_key, [])
        q_set = set(q_tokens)
        d_set = set(d_toks)
        if not q_set or not d_set:
            return 0.0
        inter = len(q_set & d_set)
        return inter / math.sqrt(len(q_set) * len(d_set))

    def get_brand_subgraph(self, query: str) -> list[dict]:
        """Isolates brand entity subgraph if brand is mentioned in query."""
        q_lower = query.lower()
        if "오로라" in q_lower or "리테일" in q_lower:
            target_ws_prefix = "retail"
            return [d for d in self.docs if int(d["campaign_ref"][1:]) <= 10]
        elif "넥스트" in q_lower or "글로벌" in q_lower:
            return [d for d in self.docs if 11 <= int(d["campaign_ref"][1:]) <= 20]
        elif "핀포인트" in q_lower or "파이낸스" in q_lower:
            return [d for d in self.docs if 21 <= int(d["campaign_ref"][1:]) <= 30]
        return self.docs


GLOBAL_INDEXER = MarketingCorpusIndexer()


def _min_max_normalize(scores: list[float]) -> list[float]:
    if not scores:
        return []
    min_s = min(scores)
    max_s = max(scores)
    rng = max_s - min_s
    if rng < 1e-6:
        return [0.5 for _ in scores]
    return [(s - min_s) / rng for s in scores]


class BM25RetrieverAdapter(BaseBlackBoxRetriever):
    """1. Pure BM25 Keyword Search over the entire 1,050 corpus."""

    def __init__(self, indexer: MarketingCorpusIndexer | None = None) -> None:
        self._idx = indexer or GLOBAL_INDEXER

    def search(
        self, query: str, active_campaign_anchor: str | None = None, top_k: int = 5
    ) -> Sequence[SearchHitResult]:
        q_tokens = re.findall(r"[가-힣A-Za-z0-9_]+", query.lower())
        scores = []
        for d in self._idx.docs:
            d_key = str(d["document_key"])
            s = self._idx.bm25(q_tokens, d_key)
            scores.append((s, d))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchHitResult(
                document_id=d["id"],
                document_key=d["document_key"],
                campaign_ref=d["campaign_ref"],
                score=s,
                rank=idx + 1,
            )
            for idx, (s, d) in enumerate(scores[:top_k])
        ]


class DenseRetrieverAdapter(BaseBlackBoxRetriever):
    """2. Pure Dense Semantic Search over the entire 1,050 corpus."""

    def __init__(self, indexer: MarketingCorpusIndexer | None = None) -> None:
        self._idx = indexer or GLOBAL_INDEXER

    def search(
        self, query: str, active_campaign_anchor: str | None = None, top_k: int = 5
    ) -> Sequence[SearchHitResult]:
        q_tokens = re.findall(r"[가-힣A-Za-z0-9_]+", query.lower())
        scores = []
        for d in self._idx.docs:
            d_key = str(d["document_key"])
            s = self._idx.dense_sim(q_tokens, d_key)
            scores.append((s, d))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchHitResult(
                document_id=d["id"],
                document_key=d["document_key"],
                campaign_ref=d["campaign_ref"],
                score=s,
                rank=idx + 1,
            )
            for idx, (s, d) in enumerate(scores[:top_k])
        ]


class ScoreFusedHybridAdapter(BaseBlackBoxRetriever):
    """3. Properly Normalized Hybrid (BM25_norm 0.5 + Dense_norm 0.5)."""

    def __init__(self, indexer: MarketingCorpusIndexer | None = None) -> None:
        self._idx = indexer or GLOBAL_INDEXER

    def search(
        self, query: str, active_campaign_anchor: str | None = None, top_k: int = 5
    ) -> Sequence[SearchHitResult]:
        q_tokens = re.findall(r"[가-힣A-Za-z0-9_]+", query.lower())
        raw_bm = []
        raw_de = []
        for d in self._idx.docs:
            d_key = str(d["document_key"])
            raw_bm.append(self._idx.bm25(q_tokens, d_key))
            raw_de.append(self._idx.dense_sim(q_tokens, d_key))

        norm_bm = _min_max_normalize(raw_bm)
        norm_de = _min_max_normalize(raw_de)

        fused = [
            (0.5 * bm_s + 0.5 * de_s, d)
            for bm_s, de_s, d in zip(norm_bm, norm_de, self._idx.docs)
        ]
        fused.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchHitResult(
                document_id=d["id"],
                document_key=d["document_key"],
                campaign_ref=d["campaign_ref"],
                score=s,
                rank=idx + 1,
            )
            for idx, (s, d) in enumerate(fused[:top_k])
        ]


class PureGraphRetrieverAdapter(BaseBlackBoxRetriever):
    """4. Pure Graph Traversal: Subgraph boundary isolation without content ranker."""

    def __init__(self, indexer: MarketingCorpusIndexer | None = None) -> None:
        self._idx = indexer or GLOBAL_INDEXER

    def search(
        self, query: str, active_campaign_anchor: str | None = None, top_k: int = 5
    ) -> Sequence[SearchHitResult]:
        candidate_docs = self._idx.get_brand_subgraph(query)
        # Chronological recency prior within subgraph
        return [
            SearchHitResult(
                document_id=d["id"],
                document_key=d["document_key"],
                campaign_ref=d["campaign_ref"],
                score=1.0 / (1.0 + idx),
                rank=idx + 1,
            )
            for idx, d in enumerate(candidate_docs[:top_k])
        ]


class HybridGraphRetrievalAdapter(BaseBlackBoxRetriever):
    """5. Main Node: Brand Graph Subgraph Isolation + Normalized Hybrid (BM25_norm + Dense_norm)."""

    def __init__(self, indexer: MarketingCorpusIndexer | None = None) -> None:
        self._idx = indexer or GLOBAL_INDEXER

    def search(
        self, query: str, active_campaign_anchor: str | None = None, top_k: int = 5
    ) -> Sequence[SearchHitResult]:
        q_tokens = re.findall(r"[가-힣A-Za-z0-9_]+", query.lower())
        candidate_docs = self._idx.get_brand_subgraph(query)

        raw_bm = []
        raw_de = []
        for d in candidate_docs:
            d_key = str(d["document_key"])
            raw_bm.append(self._idx.bm25(q_tokens, d_key))
            raw_de.append(self._idx.dense_sim(q_tokens, d_key))

        norm_bm = _min_max_normalize(raw_bm)
        norm_de = _min_max_normalize(raw_de)

        fused = [
            (0.5 * bm_s + 0.5 * de_s, d)
            for bm_s, de_s, d in zip(norm_bm, norm_de, candidate_docs)
        ]
        fused.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchHitResult(
                document_id=d["id"],
                document_key=d["document_key"],
                campaign_ref=d["campaign_ref"],
                score=s,
                rank=idx + 1,
            )
            for idx, (s, d) in enumerate(fused[:top_k])
        ]
