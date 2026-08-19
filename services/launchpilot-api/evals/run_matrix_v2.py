from __future__ import annotations

import json
from pathlib import Path

from launchpilot.evaluation.experiments.contracts import (
    ChunkingConfig, ChunkingMethod, ExperimentManifest, FusionMethod, RetrievalConfig, RetrievalMethod
)
from launchpilot.evaluation.experiments.local_adapters import (
    MarketingCrossFeatureReranker, MarketingDenseEncoder, KoreanTfidfSparseEncoder
)
from launchpilot.evaluation.experiments.retrievers import RetrieverFactory
from launchpilot.evaluation.experiments.runner import RetrievalExperimentRunner, load_golden_document_benchmark
from launchpilot.evaluation.experiments.perturbation import PerturbationLevel, create_naturalized_cases

root = Path("services/launchpilot-api/evals/golden/golden-v2")
docs, cases, raw_manifest = load_golden_document_benchmark(root)

factory = RetrieverFactory(
    dense_encoder=MarketingDenseEncoder(dimensions=512),
    sparse_encoder=KoreanTfidfSparseEncoder(),
    reranker=MarketingCrossFeatureReranker(),
)
runner = RetrievalExperimentRunner(factory)

chunkers = [
    ("Whole Doc", ChunkingConfig(method=ChunkingMethod.WHOLE_DOCUMENT, version="whole-v1")),
    ("Sentence", ChunkingConfig(method=ChunkingMethod.SENTENCE, version="sent-v1")),
    ("Fixed 400", ChunkingConfig(method=ChunkingMethod.FIXED_TOKEN, max_tokens=400, overlap_tokens=50, version="fixed-400-v1")),
]

perturbations = [
    ("Clean (Template)", PerturbationLevel.CLEAN),
    ("Colloquial (Synonym)", PerturbationLevel.COLLOQUIAL_SYNONYM),
    ("Jargon (Marketer Slang)", PerturbationLevel.MARKETER_JARGON),
]

# Pure 1st-Stage Retrievers only (ReRanker is separated into downstream Post-Retrieval stage)
retrievers = [
    ("BM25", RetrievalConfig(method=RetrievalMethod.BM25, version="bm25-v1", top_k=5, search_scope="workspace")),
    ("Dense", RetrievalConfig(method=RetrievalMethod.DENSE, version="dense-v1", top_k=5, search_scope="workspace", provider="dense")),
    ("Hybrid (RRF)", RetrievalConfig(method=RetrievalMethod.HYBRID, version="hybrid-rrf-v1", top_k=5, search_scope="workspace", fusion=FusionMethod.RRF, rrf_k=60, provider="dense")),
]

results = []
print("=== PURE 1ST-STAGE RETRIEVAL MATRIX EXPERIMENT (GOLDEN V2, ALL 900 DOCS) ===")
print("Total combinations: " + str(len(perturbations) * len(chunkers) * len(retrievers)) + " runs\n")

for p_label, p_level in perturbations:
    p_cases = create_naturalized_cases(cases, p_level)
    for c_label, c_cfg in chunkers:
        for r_label, r_cfg in retrievers:
            manifest = ExperimentManifest(
                matrix_version="matrix-v2-pure-retrieval",
                golden_version="golden-v2",
                corpus_version="synthetic-pg-doc-snapshot-v2",
                split="tune",
                chunker=c_cfg,
                retriever=r_cfg,
            )
            res = runner.run(manifest, docs, p_cases)
            m = res.aggregate_metrics
            rec = m.get("recall_at_k", 0.0)
            mrr = m.get("mrr_at_k", 0.0)
            ndcg = m.get("ndcg_at_k", 0.0)
            prec = m.get("context_precision_at_k", 0.0)
            lat = m.get("p95_latency_ms", 0.0)
            results.append({
                "perturbation": p_label,
                "chunker": c_label,
                "retriever": r_label,
                "recall_at_5": rec,
                "mrr_at_5": mrr,
                "ndcg_at_5": ndcg,
                "precision_at_5": prec,
                "p95_ms": lat,
            })

out_path = Path("services/launchpilot-api/evals/retrieval_experiment_results_v2.json")
out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print("Experiments successfully completed! Saved to " + str(out_path) + "\n")

col1 = "Perturbation"
col2 = "Chunker"
col3 = "Retriever"
col4 = "Recall@5"
col5 = "MRR@5"
col6 = "nDCG@5"

print(f"| {col1:<24} | {col2:<10} | {col3:<16} | {col4:<8} | {col5:<8} | {col6:<8} |")
print("|" + "-" * 26 + "|" + "-" * 12 + "|" + "-" * 18 + "|" + "-" * 10 + "|" + "-" * 10 + "|" + "-" * 10 + "|")
for row in results:
    p = row["perturbation"]
    c = row["chunker"]
    r = row["retriever"]
    rec_s = f"{row["recall_at_5"]:.4f}"
    mrr_s = f"{row["mrr_at_5"]:.4f}"
    ndcg_s = f"{row["ndcg_at_5"]:.4f}"
    print(f"| {p:<24} | {c:<10} | {r:<16} | {rec_s:<8} | {mrr_s:<8} | {ndcg_s:<8} |")
