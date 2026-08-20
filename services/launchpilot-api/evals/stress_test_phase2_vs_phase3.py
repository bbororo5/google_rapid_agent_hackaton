import os
import re
import time
import json
import sqlite3
from datetime import datetime, UTC
from uuid import UUID, uuid4

from launchpilot.bootstrap.wiring import agent_model
from launchpilot.campaigns.contracts.access import CampaignScope
from launchpilot.knowledge.contracts.retrieval import TextSearchHit, DocumentType, CampaignDocument
from launchpilot.performance.contracts.retrieval import CampaignPerformance, CampaignSummary, CampaignMetricQuery
from launchpilot.analysis.scope import ExecutionScope
from launchpilot.analysis.tools import CampaignToolset
from launchpilot.analysis.graph_retriever import MarketingKnowledgeGraph
from launchpilot.analysis.reranker import MarketingDomainReranker
from launchpilot.analysis.graph import AnalysisGraph, RouterNode, AgentNode
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

# Phoenix Instrumentation
try:
    from openinference.instrumentation.langchain import LangChainInstrumentor
    LangChainInstrumentor().instrument()
except Exception:
    pass

DB_PATH = "services/launchpilot-api/local_launchpilot.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# Fetch Campaign Info
conn = get_conn()
c = conn.cursor()
c0001_info = c.execute("SELECT id, workspace_id FROM campaigns WHERE campaign_code = 'C0001'").fetchone()
c0001_id, ws_id = UUID(c0001_info[0]), UUID(c0001_info[1])

c0002_info = c.execute("SELECT id, workspace_id FROM campaigns WHERE campaign_code = 'C0002'").fetchone()
c0002_id = UUID(c0002_info[0]) if c0002_info else c0001_id

scope = ExecutionScope(workspace_id=str(ws_id), campaign_id=str(c0001_id), reference_now=datetime(2025, 6, 1, tzinfo=UTC))
camp_scope = CampaignScope(campaign_id=c0001_id, workspace_id=ws_id, user_id=uuid4())

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
                name="오로라 리테일 상반기 메인 캠페인",
                goal="ROAS 극대화",
                period_start=datetime(2025, 1, 1).date(),
                period_end=datetime(2025, 4, 30).date(),
                target_metrics=(),
            ),
            metrics=(),
        )

# 3 Realistic Adversarial Stress Cases
STRESS_CASES = [
    {
        "id": "stress_1_temporal_collision",
        "title": "시계열 방해물 충돌: 3월 초순 입찰가 미세 조정 차수 판별",
        "query": "오로라 리테일에서 3월 초순에 단가 불안정해서 주간 입찰가 미세 조정 조치했던 일지가 몇 차 일지인지 찾아서 당시 조치 내용 요약해줘",
        "ground_truth_target": "5차 정기 주간 운영 및 입찰가 조정 일지",
        "key_facts": ["5차", "입찰가", "미세 조정", "3월"]
    },
    {
        "id": "stress_2_cross_campaign",
        "title": "동일 광고주 내 캠페인 크로스 판별: 2월 1주차 배너 교체 캠페인 판별",
        "query": "오로라 리테일 상반기 캠페인 중에 2월 1주차에 메인 배너 클릭률 급락해서 신규 B안 할인 배너로 전면 교체 집행했던 캠페인이 C0001인지 C0002인지 판별하고 당시 교체 근거 찾아줘",
        "ground_truth_target": "C0001 2월 1주차 이미지 배너 소재 교체 일지",
        "key_facts": ["C0001", "B안", "클릭률", "배너"]
    },
    {
        "id": "stress_3_3hop_causal",
        "title": "지표-조치-회고 3-Hop 결합 추론: 1월 말 삭감 조치와 2월 회고 리포트의 결론",
        "query": "오로라 리테일 C0001에서 1월 말에 예산 소진율 120% 초과로 일 예산 15% 일시 삭감 조치한 이후, 2월 월간 성과 분석서에서 이 페이싱 조치의 효과와 ROAS 변화를 어떻게 평가했는지 연결해서 설명해줘",
        "ground_truth_target": "1월 말 예산 페이싱 속도 재조정 메모 + 2월 월간 분석 리포트",
        "key_facts": ["15% 일시 삭감", "소진율", "2월", "ROAS", "안정화"]
    }
]

def build_pipeline(use_reranker: bool):
    toolset = CampaignToolset(
        scope=camp_scope,
        retrieval=LocalPerfReader(c0001_id, ws_id),
        text_retrieval=LocalDocReader(c0001_id, ws_id),
        graph=MarketingKnowledgeGraph(get_conn()),
    )
    tools = toolset.tools()
    base_llm = agent_model()
    model_with_tools = base_llm.bind_tools(tools)
    
    if not use_reranker:
        # Phase 2 topology: tools -> agent directly (No In-Loop Reranker)
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
        # Phase 3 topology: tools -> reranker -> agent (In-Loop Evidence Organizer)
        return AnalysisGraph(model_with_tools=model_with_tools, tools=tools, scope=scope)

def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return " ".join(parts)
    return str(content)

def evaluate_case(answer, case: dict):
    ans_text = extract_text(answer)
    ans_lower = ans_text.lower()
    matched_facts = [f for f in case["key_facts"] if f.lower() in ans_lower]
    passed = len(matched_facts) >= 2 and len(ans_text.strip()) > 30
    return {
        "passed": passed,
        "matched_facts": matched_facts,
        "status": "GROUNDED_FAITHFUL" if passed else "UNGROUNDED_MISS",
        "clean_text": ans_text
    }

def run_stress_test():
    print("=================================================================")
    print("🥊 REALISTIC ADVERSARIAL STRESS TEST: PHASE 2 vs PHASE 3")
    print("=================================================================\n")

    results = {"phase2_raw": [], "phase3_reranker": []}

    # 1. Test Phase 2 (Without In-Loop Reranker)
    print(">>> [TESTING PHASE 2: Raw Retrieval without In-Loop Reranker] <<<")
    app_p2 = build_pipeline(use_reranker=False)
    for idx, c in enumerate(STRESS_CASES, 1):
        t0 = time.perf_counter()
        transcript = app_p2.invoke({"messages": [c["query"]]})
        dur = time.perf_counter() - t0
        ans = transcript["messages"][-1].content
        tools_called = [m.name for m in transcript["messages"] if hasattr(m, "name") and m.name]
        eval_res = evaluate_case(ans, c)
        print(f"  [{idx}/3] {c["id"]} | Status: {eval_res["status"]} | Lat: {dur:.2f}s | Tools: {tools_called}")
        results["phase2_raw"].append({
            "case_id": c["id"],
            "title": c["title"],
            "status": eval_res["status"],
            "latency": dur,
            "tools": tools_called,
            "answer": ans
        })

    # 2. Test Phase 3 (With In-Loop Reranker)
    print("\n>>> [TESTING PHASE 3: With In-Loop EvidenceOrganizer (Reranker)] <<<")
    app_p3 = build_pipeline(use_reranker=True)
    for idx, c in enumerate(STRESS_CASES, 1):
        t0 = time.perf_counter()
        transcript = app_p3.invoke(c["query"])
        dur = time.perf_counter() - t0
        ans = transcript.final_answer()
        tools_called = [m.name for m in transcript.messages if hasattr(m, "name") and m.name]
        eval_res = evaluate_case(ans, c)
        print(f"  [{idx}/3] {c["id"]} | Status: {eval_res["status"]} | Lat: {dur:.2f}s | Tools: {tools_called}")
        results["phase3_reranker"].append({
            "case_id": c["id"],
            "title": c["title"],
            "status": eval_res["status"],
            "latency": dur,
            "tools": tools_called,
            "answer": ans
        })

    with open("services/launchpilot-api/evals/stress_test_comparison_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\n🎉 Stress test completed successfully!")

if __name__ == "__main__":
    run_stress_test()
