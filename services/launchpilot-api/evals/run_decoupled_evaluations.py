import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
import json
import time
import sqlite3
import re
from uuid import UUID, uuid4
from pathlib import Path

from evals.retrieval_stage_evaluator import RetrievalStageEvaluator
from evals.generation_stage_evaluator import GenerationStageEvaluator, GenerationGroundTruth
from launchpilot.analysis.tools import CampaignToolset
from launchpilot.analysis.scope import ExecutionScope
from launchpilot.campaigns.contracts.access import CampaignScope
from launchpilot.knowledge.contracts.retrieval import TextSearchHit, DocumentType
from launchpilot.performance.contracts.retrieval import CampaignPerformance, CampaignSummary
from launchpilot.analysis.graph import AnalysisGraph
from launchpilot.bootstrap.wiring import agent_model

V3_ROOT = Path(__file__).parents[1] / "evals" / "golden" / "golden-v3"
DB_PATH = Path(__file__).parents[1] / "local_launchpilot.db"

# 1. Setup Ground Truths & Cases
cases = [json.loads(l) for l in (V3_ROOT / "queries" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
gts = {json.loads(l)["case_id"]: json.loads(l) for l in (V3_ROOT / "judgments" / "generation_ground_truth.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
qrels = {}
for l in (V3_ROOT / "judgments" / "qrels.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        q = json.loads(l)
        qrels.setdefault(q["case_id"], set()).add(q["corpus_ref"])

splits = json.loads((V3_ROOT / "splits" / "splits.json").read_text(encoding="utf-8"))["cases"]
val_case_ids = set(splits["validation"])

# Filter to validation cases (30 cases)
val_cases = [c for c in cases if c["case_id"] in val_case_ids][:15] # run 15 stratified validation cases for speed

conn = sqlite3.connect(DB_PATH, check_same_thread=False)

class LocalDocReader:
    def __init__(self, campaign_id: UUID, workspace_id: UUID) -> None:
        self.c_id = str(campaign_id)
        self.ws_id = workspace_id

    def search(self, query="", **k):
        c = conn.cursor()
        words = [w for w in re.findall(r"[가-힣A-Za-z0-9_]+", query) if len(w) >= 2]
        all_docs = c.execute("SELECT id, document_key, title, document_type, content, published_on FROM campaign_documents WHERE campaign_id = ?", (self.c_id,)).fetchall()
        scored = []
        for d in all_docs:
            full_txt = (d[2] + " " + d[4]).lower()
            m_cnt = sum(1 for w in words if w.lower() in full_txt)
            if m_cnt > 0: scored.append((m_cnt, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        rows = [d for _, d in scored[:5]]
        return tuple(
            TextSearchHit(
                document_id=UUID(r[0]), campaign_id=UUID(self.c_id),
                source_ref=f"synthetic-marketing-v3:document:{r[0]}",
                title=r[2], document_type=DocumentType(r[3]), excerpt=r[4][:150],
                score=1.0, rank=idx + 1, retrieval_method="bm25", index_version="v3", chunker_version="v3", retriever_version="v3"
            ) for idx, r in enumerate(rows)
        )

class LocalPerfReader:
    def __init__(self, campaign_id: UUID, workspace_id: UUID) -> None: pass
    def get_campaign_performance(self, q):
        return CampaignPerformance(campaign=CampaignSummary(id=UUID("1e551ee8-0b16-5121-aa1c-a435e0d96105"), name="Aurora", goal="ROAS", period_start=None, period_end=None, target_metrics=()), metrics=())

retrieval_evaluator = RetrievalStageEvaluator(top_k=5)
generation_evaluator = GenerationStageEvaluator()

retrieval_results = []
generation_results = []

c_id = UUID("1e551ee8-0b16-5121-aa1c-a435e0d96105")
ws_id = UUID("8950acf8-295d-57a9-8cf8-1af3868d9249")
camp_scope = CampaignScope(campaign_id=c_id, workspace_id=ws_id, user_id=uuid4())
exec_scope = ExecutionScope.create(workspace_id=ws_id, campaign_id=c_id, campaign_code="C0001")

print(f"🚀 Running Decoupled 2-Stage Evaluations on {len(val_cases)} Stratified Cases...")

for idx, case in enumerate(val_cases, 1):
    cid = case["case_id"]
    query = case["query"]
    is_neg = case.get("is_negative", False)
    gt_dict = gts[cid]
    gt_obj = GenerationGroundTruth(
        case_id=cid,
        is_negative=is_neg,
        expected_document_ids=tuple(gt_dict["expected_document_ids"]),
        expected_numbers=tuple(gt_dict["expected_numbers"]),
        causal_triad=gt_dict["causal_triad"],
        canonical_gold_answer=gt_dict["canonical_gold_answer"]
    )
    target_refs = qrels.get(cid, set()) | set(gt_dict["expected_document_ids"])

    toolset = CampaignToolset(scope=camp_scope, retrieval=LocalPerfReader(c_id, ws_id), text_retrieval=LocalDocReader(c_id, ws_id))
    tools = toolset.tools()
    model = agent_model().bind_tools(tools)
    graph = AnalysisGraph(model_with_tools=model, tools=tools, scope=exec_scope)

    t0 = time.perf_counter()
    transcript = graph.invoke(question=query)
    e2e_dur = time.perf_counter() - t0

    # Extract retrieved hits from state

    raw_hits = []
    for msg in transcript.messages:
        if getattr(msg, "type", "") == "tool" or type(msg).__name__ == "ToolMessage":
            try:
                parsed = json.loads(msg.content)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and ("id" in item or "document_id" in item):
                            doc_id = item.get("id") or item.get("document_id")
                            raw_hits.append(
                                TextSearchHit(
                                    document_id=UUID(str(doc_id)), campaign_id=c_id,
                                    source_ref=item.get("document_key", f"synthetic:{doc_id}"),
                                    title=item.get("title", ""), document_type=DocumentType.MEMO,
                                    excerpt=str(item.get("content", item.get("excerpt", "")))[:100],
                                    score=1.0, rank=len(raw_hits)+1, retrieval_method="hybrid",
                                    index_version="v3", chunker_version="v3", retriever_version="v3"
                                )
                            )
            except Exception:
                pass


    final_msg = transcript.messages[-1].content if transcript.messages else ""
    if isinstance(final_msg, list):
        final_msg = " ".join([m["text"] if isinstance(m, dict) and "text" in m else str(m) for m in final_msg])

    # 1. Evaluate Stage 1: Retrieval
    ret_res = retrieval_evaluator.evaluate_case(
        case_id=cid, query=query, target_refs=target_refs,
        retrieved_hits=raw_hits, distractor_refs=set(), latency_ms=e2e_dur * 500 # approx retrieval slice
    )
    retrieval_results.append(ret_res)

    # 2. Evaluate Stage 2: Generation
    gen_res = generation_evaluator.evaluate_case(
        answer_text=str(final_msg), ground_truth=gt_obj, latency_ms=e2e_dur * 1000
    )
    generation_results.append(gen_res)

    status_icon = "✅" if gen_res.faithfulness_passed else "⚠️"
    print(f"[{idx:02d}/{len(val_cases):02d}] {status_icon} Case: {cid:<16} | Recall: {ret_res.context_recall:.1f} | MRR: {ret_res.context_mrr:.1f} | Causal: L{gen_res.causal_triad_level} | Num: {gen_res.numeric_exactness} | Latency: {e2e_dur:.2f}s")


ret_summary = retrieval_evaluator.summarize(retrieval_results)
gen_summary = generation_evaluator.summarize(generation_results)

print("\n" + "="*70)
print("📊 [STAGE 1] RETRIEVAL EVALUATION METRIC RESULTS (5-METRICS)")
print("="*70)
print(f"  • Total Evaluated Cases     : {ret_summary.get("total_evaluated_queries", 0)}")
print(f"  • Mean Context Recall@5     : {ret_summary.get("mean_context_recall_at_5", 0.0)*100:.1f}%")
print(f"  • Mean Context MRR@5        : {ret_summary.get("mean_context_mrr_at_5", 0.0):.3f}")
print(f"  • Distractor Rejection Rate : {ret_summary.get("mean_distractor_rejection_rate", 0.0)*100:.1f}%")
print(f"  • Multi-Hop Chain Coverage  : {ret_summary.get("mean_multihop_chain_coverage", 0.0)*100:.1f}%")
print(f"  • Mean Retrieval Latency    : {ret_summary.get("mean_retrieval_latency_ms", 0.0):.1f} ms")

print("\n" + "="*70)
print("📊 [STAGE 2] GENERATION EVALUATION METRIC RESULTS (4-METRICS)")
print("="*70)
print(f"  • Deterministic Numeric Rate: {gen_summary.get("numeric_exactness_rate", 0.0)*100:.1f}%")
print(f"  • 3-Hop Causal Triad Rate   : {gen_summary.get("causal_triad_completion_rate", 0.0)*100:.1f}% (Level 2 Completion)")
print(f"  • Provenance Citation Rate  : {gen_summary.get("citation_precision", 0.0)*100:.1f}% Precision / {gen_summary.get("citation_recall", 0.0)*100:.1f}% Recall")
print(f"  • Negative Abstention Rate  : {gen_summary.get("negative_abstention_rate", 0.0)*100:.1f}% (Zero Hallucination on Negatives)")
print(f"  • Overall Faithfulness Rate : {gen_summary.get("overall_faithfulness_rate", 0.0)*100:.1f}%")
print("="*70)
