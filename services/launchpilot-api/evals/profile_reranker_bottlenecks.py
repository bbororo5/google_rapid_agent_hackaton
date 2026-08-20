import time
import json
from uuid import uuid4
from datetime import datetime, UTC
from launchpilot.knowledge.contracts.retrieval import TextSearchHit, DocumentType
from launchpilot.bootstrap.wiring import agent_model
from launchpilot.analysis.reranker import MarketingDomainReranker

# Mock candidate hits for profiling
sample_hits = [
    TextSearchHit(
        document_id=uuid4(),
        campaign_id=uuid4(),
        source_ref="synthetic-marketing-v3:document:1",
        title=f"C0001 {i}차 정기 주간 운영 및 입찰가 조정 일지",
        document_type=DocumentType.MEMO,
        excerpt="정기 모니터링 수행. 타겟 CPA 범위 내 유지 중이며 키워드 입찰가 5% 미세 조정 완료.",
        score=1.0 - (i * 0.05),
        rank=i,
        retrieval_method="bm25",
        index_version="v3",
        chunker_version="v3",
        retriever_version="v3",
    )
    for i in range(1, 11)
]

def profile_reranker_deep():
    print("=================================================================")
    print("🔬 DEEP PROFILING OF RERANKER BOTTLENECKS (MILLISECOND LEVEL)")
    print("=================================================================\n")

    # 1. Measure Model Instantiation & ADC Auth Overhead
    t0 = time.perf_counter()
    model = agent_model()
    t_model_init = (time.perf_counter() - t0) * 1000
    print(f"1. [Model Instantiation & ADC Auth]: {t_model_init:.2f} ms")

    # 2. Measure Prompt Serialization Time
    t0 = time.perf_counter()
    candidates_text = [
        f"[{idx}] 제목: {h.title} (유형: {h.document_type}) | 요약: {h.excerpt[:120]}"
        for idx, h in enumerate(sample_hits, 1)
    ]
    query = "3월 초순에 정기적으로 입찰가 5% 미세 조정했던 일지 찾아줘"
    prompt = (
        "당신은 마케팅 도메인 정밀 리랭커(Listwise Reranker)입니다. "
        "사용자 질문의 요구사항(시점, 조치 대상, 질문 의도)과 가장 직접적으로 일치하는 순서대로 후보 번호들을 쉼표로 구분하여 정렬하십시오.\n"
        f"[사용자 질문]: {query}\n\n"
        f"[후보 문서 목록]:\n" + "\n".join(candidates_text) + "\n\n"
        "정답 순위 번호 목록만 쉼표로 출력 (예: 3, 1, 2, 4):"
    )
    t_prompt_build = (time.perf_counter() - t0) * 1000
    print(f"2. [Local Prompt Build & Serialization]: {t_prompt_build:.2f} ms")

    # 3. Measure First Call Remote Invocation Latency (Cold Start)
    t0 = time.perf_counter()
    res1 = model.invoke(prompt)
    t_remote_cold = (time.perf_counter() - t0) * 1000
    print(f"3. [Remote LLM Invocation (Cold Call)]: {t_remote_cold:.2f} ms ({(t_remote_cold/1000):.2f} s)")

    # 4. Measure Second Call Remote Invocation Latency (Warm Connection)
    t0 = time.perf_counter()
    res2 = model.invoke(prompt)
    t_remote_warm = (time.perf_counter() - t0) * 1000
    print(f"4. [Remote LLM Invocation (Warm Call)]: {t_remote_warm:.2f} ms ({(t_remote_warm/1000):.2f} s)")

    # 5. Measure Output Parsing & Re-indexing
    t0 = time.perf_counter()
    import re
    content_str = res2.content if hasattr(res2, "content") else str(res2)
    ordered_indices = [int(x) for x in re.findall(r"\b\d+\b", content_str) if int(x) in range(1, 11)]
    for idx in range(1, 11):
        if idx not in ordered_indices: ordered_indices.append(idx)
    t_parse = (time.perf_counter() - t0) * 1000
    print(f"5. [Output Regex Parsing & Re-ranking]: {t_parse:.2f} ms")

    # 6. Overall Summary
    total_single_call = t_prompt_build + t_remote_warm + t_parse
    print("\n=======================================================")
    print("📊 RERANKER LATENCY BUDGET BREAKDOWN")
    print("=======================================================")
    print(f"• Total Warm Rerank Call: {total_single_call:.2f} ms ({(total_single_call/1000):.2f} s)")
    print(f"  - Local Python CPU Overhead: {(t_prompt_build + t_parse):.2f} ms ({( (t_prompt_build + t_parse)/total_single_call ) * 100:.2f}%)")
    print(f"  - Remote LLM Server Computation & I/O: {t_remote_warm:.2f} ms ({( t_remote_warm/total_single_call ) * 100:.2f}%)")

if __name__ == "__main__":
    profile_reranker_deep()
