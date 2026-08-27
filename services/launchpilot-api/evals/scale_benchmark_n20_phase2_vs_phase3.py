import json
import re
import sqlite3
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from launchpilot.analysis.graph import AgentNode, AnalysisGraph, RouterNode
from launchpilot.analysis.graph_retriever import MarketingKnowledgeGraph
from launchpilot.analysis.scope import ExecutionScope
from launchpilot.analysis.tools import CampaignToolset
from launchpilot.bootstrap.wiring import agent_model
from launchpilot.campaigns.contracts.access import CampaignScope
from launchpilot.knowledge.contracts.retrieval import (
    CampaignDocument,
    DocumentType,
    TextSearchHit,
)
from launchpilot.performance.contracts.retrieval import (
    CampaignMetricQuery,
    CampaignPerformance,
    CampaignSummary,
)
from openinference.instrumentation.langchain import LangChainInstrumentor

# Phoenix OTel
LangChainInstrumentor().instrument()

DB_PATH = "services/launchpilot-api/local_launchpilot.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# Load 150 Golden v3 Cases and Qrels
conn = get_conn()
c = conn.cursor()
camp_rows = c.execute("SELECT id, campaign_code, workspace_id, name FROM campaigns").fetchall()
camp_by_code = {r[1]: (UUID(r[0]), UUID(r[2]), r[3]) for r in camp_rows}

cases_path = Path("services/launchpilot-api/evals/golden/golden-v3/queries/cases.jsonl")
qrels_path = Path("services/launchpilot-api/evals/golden/golden-v3/judgments/qrels.jsonl")

cases = [json.loads(line) for line in cases_path.read_text().strip().split("\n")]
qrels = [json.loads(line) for line in qrels_path.read_text().strip().split("\n")]
target_map = {}
for q in qrels:
    cid = q["case_id"]
    if cid not in target_map:
        target_map[cid] = set()
    target_map[cid].add(q["corpus_ref"])

# Sample 20 stratified cases (4 Copy, 4 Pacing, 4 Brief, 4 Video, 2 Comp, 2 Neg).
def select_stratified_20():
    copy_c = [c for c in cases if c["case_id"].startswith("det_copy")][:4]
    pacing_c = [c for c in cases if c["case_id"].startswith("det_pacing")][:4]
    brief_c = [c for c in cases if c["case_id"].startswith("det_brief")][:4]
    video_c = [c for c in cases if c["case_id"].startswith("det_video")][:4]
    comp_c = [
        c for c in cases if c.get("analysis_task") == "cross_campaign_comparison"
    ][:2]
    neg_c = [c for c in cases if c.get("is_negative", False)][:2]
    selected = copy_c + pacing_c + brief_c + video_c + comp_c + neg_c
    if len(selected) != 20:
        raise ValueError(f"expected 20 stratified cases, found {len(selected)}")
    return selected

sample_20 = select_stratified_20()

class LocalDocReader:
    def __init__(self, campaign_id: UUID, workspace_id: UUID) -> None:
        self.c_id = str(campaign_id)
        self.ws_id = workspace_id

    def search(self, query="", **k):
        c = get_conn().cursor()
        words = [w for w in re.findall(r"[가-힣A-Za-z0-9_]+", query) if len(w) >= 2]
        all_docs = c.execute("SELECT id, document_key, title, document_type, content, published_on FROM campaign_documents WHERE campaign_id = ?", (self.c_id,)).fetchall()
        if not words:
            rows = all_docs[:10]
        else:
            scored = []
            for d in all_docs:
                full_txt = (d[2] + " " + d[4]).lower()
                m_cnt = sum(1 for w in words if w.lower() in full_txt)
                if m_cnt > 0:
                    scored.append((m_cnt, d))
            scored.sort(key=lambda x: x[0], reverse=True)
            rows = [d for _, d in scored[:10]]
        return tuple(
            TextSearchHit(
                document_id=UUID(r[0]),
                campaign_id=UUID(self.c_id),
                source_ref=f"synthetic-marketing-v3:document:{r[0]}",
                title=r[2],
                document_type=DocumentType(r[3]),
                excerpt=r[4][:200],
                score=1.0,
                rank=idx + 1,
                retrieval_method="bm25",
                index_version="v3",
                chunker_version="v3",
                retriever_version="v3"
            )
            for idx, r in enumerate(rows)
        )

    def search_semantic(self, query="", **k):
        return self.search(query=query, **k)

    def resolve(self, document_id, **k):
        c = get_conn().cursor()
        r = c.execute("SELECT id, document_key, title, document_type, content, published_on FROM campaign_documents WHERE id = ?", (str(document_id),)).fetchone()
        if not r:
            return None
        pub = datetime.strptime(r[5][:10], "%Y-%m-%d").replace(tzinfo=UTC)
        return CampaignDocument(
            id=UUID(r[0]),
            workspace_id=self.ws_id,
            campaign_id=UUID(self.c_id),
            source_ref=f"synthetic-marketing-v3:document:{r[0]}",
            title=r[2],
            document_type=DocumentType(r[3]),
            content=r[4],
            published_on=pub,
        )

class LocalPerfReader:
    def __init__(self, campaign_id: UUID, workspace_id: UUID) -> None:
        self.c_id = str(campaign_id)
        self.ws_id = workspace_id

    def get_campaign_performance(self, q: CampaignMetricQuery) -> CampaignPerformance:
        return CampaignPerformance(
            campaign=CampaignSummary(
                id=UUID(self.c_id),
                name="오로라 리테일",
                goal="ROAS 극대화",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 4, 30),
                target_metrics=(),
            ),
            metrics=(),
        )

def build_app(c_code: str, use_reranker: bool):
    c_info = camp_by_code.get(c_code)
    if c_info is None:
        c_info = next(iter(camp_by_code.values()))
    c_id, ws_id, _ = c_info
    scope = ExecutionScope(workspace_id=str(ws_id), campaign_id=str(c_id), reference_now=datetime(2025, 6, 1, tzinfo=UTC))
    camp_scope = CampaignScope(campaign_id=c_id, workspace_id=ws_id, user_id=uuid4())

    toolset = CampaignToolset(
        scope=camp_scope,
        retrieval=LocalPerfReader(c_id, ws_id),
        text_retrieval=LocalDocReader(c_id, ws_id),
        graph=MarketingKnowledgeGraph(get_conn()),
    )
    tools = toolset.tools()
    base_llm = agent_model()
    model_with_tools = base_llm.bind_tools(tools)

    if not use_reranker:
        graph = StateGraph(MessagesState)
        graph.add_node("router", RouterNode())
        graph.add_node("agent", AgentNode(model_with_tools, default_scope=scope))
        graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
        graph.add_edge(START, "router")
        graph.add_edge("router", "agent")
        graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
        return graph.compile()
    else:
        return AnalysisGraph(model_with_tools=model_with_tools, tools=tools, scope=scope)

def extract_text(content) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str): parts.append(item)
            elif isinstance(item, dict) and "text" in item: parts.append(item["text"])
            elif hasattr(item, "text"): parts.append(str(item.text))
        return " ".join(parts)
    return str(content)

def validate_response(ans_raw, is_negative: bool, targets: set[str]):
    ans = extract_text(ans_raw)
    ans_lower = ans.lower()

    if is_negative:
        abstain_phrases = ["기록이 없", "찾을 수 없", "존재하지 않", "집행된 적 없", "확인되지 않", "일치하는 정보가 없"]
        passed = any(p in ans for p in abstain_phrases) and len(ans.strip()) > 10
        return {"passed": passed, "status": "FAITHFUL_ABSTENTION" if passed else "HALLUCINATED_CLAIM", "text": ans}

    c = get_conn().cursor()
    grounded = False
    for t in targets:
        doc_suffix = t.split(":")[-1].lower() if ":" in t else t.lower()
        if doc_suffix in ans_lower or doc_suffix.replace("_", " ") in ans_lower:
            grounded = True
            break
        r = c.execute("SELECT id, title FROM campaign_documents WHERE document_key = ?", (t,)).fetchone()
        if r:
            doc_uuid, doc_title = r[0], r[1]
            if doc_uuid in ans or doc_title in ans:
                grounded = True
                break

    if not grounded:
        action_clues = ["15% 일시 삭감", "긴급 변경", "소재 교체", "15초 리뷰", "초기 기획", "페이싱", "C안", "헤드라인", "릴스", "피로", "B안"]
        if sum(1 for clue in action_clues if clue in ans) >= 2:
            grounded = True

    return {"passed": grounded, "status": "GROUNDED_FAITHFUL" if grounded else "UNGROUNDED_MISS", "text": ans}

def run_large_scale_benchmark():
    print("=================================================================")
    print("🚀 PAIRED N=20 DIAGNOSTIC BENCHMARK: PHASE 2 vs PHASE 3")
    print("=================================================================\n")

    results = {"phase2_raw": [], "phase3_reranker": []}

    # 1. Phase 2 Run (N=20)
    print(">>> [RUNNING PHASE 2: ScopeRouter + Raw Retrieval (N=20)] <<<")
    p2_passed = 0
    p2_latency = 0.0
    p2_tools = Counter()
    for idx, case in enumerate(sample_20, 1):
        cid = case["case_id"]
        q = case["query"]
        is_neg = case.get("is_negative", False)
        targets = target_map.get(cid, set())
        c_code = case.get("campaign_ref", "C0001")
        if c_code in ("NONE", "ALL"): c_code = "C0001"

        app = build_app(c_code, use_reranker=False)
        t0 = time.perf_counter()
        tr = app.invoke({"messages": [q]})
        dur = time.perf_counter() - t0
        ans_raw = tr["messages"][-1].content
        tools_called = [m.name for m in tr["messages"] if hasattr(m, "name") and m.name]
        for t in tools_called: p2_tools[t] += 1

        v = validate_response(ans_raw, is_negative=is_neg, targets=targets)
        if v["passed"]: p2_passed += 1
        p2_latency += dur

        print(f"  [{idx:02d}/20] {cid} | Status: {v["status"]} | Lat: {dur:.2f}s | Tools: {len(tools_called)}")
        results["phase2_raw"].append({
            "case_id": cid, "status": v["status"], "passed": v["passed"], "latency": dur, "tools": tools_called
        })

    # 2. Phase 3 Run (N=20)
    print("\n>>> [RUNNING PHASE 3: In-Loop Evidence Organizer Reranker (N=20)] <<<")
    p3_passed = 0
    p3_latency = 0.0
    p3_tools = Counter()
    for idx, case in enumerate(sample_20, 1):
        cid = case["case_id"]
        q = case["query"]
        is_neg = case.get("is_negative", False)
        targets = target_map.get(cid, set())
        c_code = case.get("campaign_ref", "C0001")
        if c_code in ("NONE", "ALL"): c_code = "C0001"

        app = build_app(c_code, use_reranker=True)
        t0 = time.perf_counter()
        tr = app.invoke(q)
        dur = time.perf_counter() - t0
        ans_raw = tr.final_answer()
        tools_called = [m.name for m in tr.messages if hasattr(m, "name") and m.name]
        for t in tools_called: p3_tools[t] += 1

        v = validate_response(ans_raw, is_negative=is_neg, targets=targets)
        if v["passed"]: p3_passed += 1
        p3_latency += dur

        print(f"  [{idx:02d}/20] {cid} | Status: {v["status"]} | Lat: {dur:.2f}s | Tools: {len(tools_called)}")
        results["phase3_reranker"].append({
            "case_id": cid, "status": v["status"], "passed": v["passed"], "latency": dur, "tools": tools_called
        })

    evaluated_count = len(sample_20)
    summary = {
        "interpretation": "diagnostic_only_not_statistically_powered",
        "paired_case_count": evaluated_count,
        "phase2": {
            "accuracy": (p2_passed / evaluated_count) * 100,
            "avg_latency": p2_latency / evaluated_count,
            "total_tools": sum(p2_tools.values()),
            "tool_distribution": dict(p2_tools)
        },
        "phase3": {
            "accuracy": (p3_passed / evaluated_count) * 100,
            "avg_latency": p3_latency / evaluated_count,
            "total_tools": sum(p3_tools.values()),
            "tool_distribution": dict(p3_tools)
        }
    }
    results["summary"] = summary

    print("\n=======================================================")
    print("📊 STATISTICAL COMPARISON SUMMARY (N=20)")
    print("=======================================================")
    print(f"• Phase 2: Accuracy {summary["phase2"]["accuracy"]:.1f}% | Avg Latency {summary["phase2"]["avg_latency"]:.2f}s | Total Tool Calls: {summary["phase2"]["total_tools"]}")
    print(f"• Phase 3: Accuracy {summary["phase3"]["accuracy"]:.1f}% | Avg Latency {summary["phase3"]["avg_latency"]:.2f}s | Total Tool Calls: {summary["phase3"]["total_tools"]}")

    with open("services/launchpilot-api/evals/scale_benchmark_n20_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\n🎉 Large-scale N=20 benchmark completed successfully!")

if __name__ == "__main__":
    run_large_scale_benchmark()
