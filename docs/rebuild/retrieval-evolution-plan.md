# Phase 3–4 — Retrieval Evolution

> 상태: **3A 완료 · 4A Golden Dataset 협업 검수 대기**

광고 분석은 정답 조건이 다른 세 종류의 Retrieval을 요구한다.

| 종류 | 데이터와 질문 | 품질 기준 |
| --- | --- | --- |
| Structured Retrieval | 기간·플랫폼별 광고 성과 수치 | 값·기간·대상의 정확성 |
| Text Retrieval | 메모·브리프·과거 분석 | 관련 passage의 순위 |
| Relationship Retrieval | Claim·Evidence·가설 연결 | 경로와 출처 추적 가능성 |

한 저장 방식으로 모두 해결하지 않고 작은 Baseline부터 같은 Dataset에서 비교한다.

## Baseline: Phase 3A

- PostgreSQL에서 ID 조회, 기간·플랫폼 필터와 metric 집계를 수행한다.
- PostgreSQL 원문을 Elasticsearch에 Whole Document 단위로 Projection하고 BM25로 검색한다.
- 검색 hit는 `source_ref`를 통해 PostgreSQL 원문으로 다시 resolve한다.
- LangGraph Agent는 서버가 주입한 Campaign 범위 안에서 Structured·BM25 Tool을 선택한다.

Dense, learned sparse, hybrid, reranker와 graph expansion은 아직 채택하지 않는다.

## Eval and evolution

```text
3A Baseline
→ 4A Golden Dataset·기준 점수
→ 3B Chunking → Dense → Sparse → Hybrid/RRF → Reranker → Graph 실험
→ 4B 같은 Dataset에서 품질·지연·복잡성 비교
```

한 번에 한 요소만 바꾸고 개선된 구성만 유지한다. Dense와 sparse는 검색 신호, hybrid는 결합, reranker는 후보 재정렬, graph는 관계 확장이므로 서로를 단순 대체하지 않는다.

## Evaluation contract

- 관찰 경로: OpenInference LangChain/LangGraph + FastAPI·HTTPX·PostgreSQL OTel → OTLP → LangSmith
- 결과 식별: `rank`, `index_version`, `chunker_version`, `retriever_version`
- Golden Dataset: 실행 UUID 대신 안정적인 scenario·campaign 참조 사용
- Structured 정답: 기대 수치·기간·출처
- Text 정답: 문서뿐 아니라 사람이 검수한 passage
- 지표: 정형 정확성, Recall@K, MRR, nDCG@K, latency와 복잡성

Chunking 이후에도 같은 passage Ground Truth를 사용해 Whole Document Baseline과 비교한다. Dataset 작성법은 [Eval README](../../services/launchpilot-api/evals/README.md)에 있다.

## Decision rule

각 실험은 구현 전에 가설과 비교 대상을 적고, Eval 후 `채택` 또는 `기각`한다. 현재 저장소 결정은 [ADR-0001](adr/0001-retrieval-storage-strategy.md), 관계형 원본 결정은 [ADR-0002](adr/0002-source-of-truth-database.md)에 있다.
