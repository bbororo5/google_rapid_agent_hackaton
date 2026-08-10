# ADR-0001: Elasticsearch를 Retrieval 진화의 주요 후보로 둔다

> 상태: **시험 채택 — Retrieval Eval로 최종 판단**
>
> 결정일: 2026-08-10

## 맥락

LaunchPilot은 여러 광고 플랫폼의 성과를 합쳐 보여 주는 대시보드가 아니라, **성과 변화의 근거를 찾고 다음 판단을 돕는 분석 Agent**를 목표로 한다. 예를 들어 “A 캠페인의 성과가 왜 하락했고 무엇을 바꿔야 하는가?”라는 질문에는 다음 과정이 함께 필요하다.

| 구분 | 필요한 이유 | 처리 방식 |
| --- | --- | --- |
| **결정적 정형 조회** (Deterministic Structured Retrieval) | 실제 하락 여부와 플랫폼·기간별 차이를 틀리지 않게 계산해야 한다. | 광고 성과 수치·기간·출처를 직접 조회·필터·집계한다. |
| **관련도 기반 텍스트 검색** (Relevance-ranked Text Retrieval) | 수치만으로 알 수 없는 과거 메모·브리프·시장 맥락에서 관련 후보를 찾아야 한다. | BM25 lexical, dense·sparse semantic, hybrid 검색으로 문서를 순위화한다. |
| **관계 기반 탐색** (Relationship Traversal) | 분석 결과가 어떤 Signal과 Evidence에서 나왔는지 설명하고 검증할 수 있어야 한다. | Claim → Evidence → 가설처럼 명시된 연결을 따라간다. |

이 구분은 저장 기술을 늘리기 위한 것이 아니다. 정형 조회만 사용하면 관련 맥락을 놓치고, 텍스트 검색만 사용하면 수치 정확성을 보장할 수 없으며, 관계 탐색만으로는 관련 문서의 우선순위를 정하기 어렵다. Agent는 사용자 질문에 따라 세 Retrieval을 선택하거나 조합하되, 각 결과의 역할을 섞지 않는다.

아카이브한 Google ADK 해커톤 프로젝트도 Elasticsearch를 사용했다. 리빌딩은 그 구현을 그대로 옮기는 작업은 아니지만, 당시 선택을 버리지 않고 현재 데이터와 목표에 맞는지 다시 검증하면 기술적 흐름을 자연스럽게 이어갈 수 있다.

## 결정

- 관계형 DB는 수치와 도메인 데이터의 source of truth로 유지한다.
- Elasticsearch는 원본이 아니라 재생성 가능한 검색 Projection의 **주요 후보**로 둔다.
- 최종 채택 여부와 사용할 검색 방식은 같은 Eval Dataset의 결과로 결정한다.

Elasticsearch가 주요 후보인 이유는 하나의 검색 엔진에서 우리가 계획한 Retrieval 진화 과정을 대부분 이어서 실험할 수 있기 때문이다.

```text
Phase 3A  Structured Retrieval + BM25 Baseline
Phase 4A  Query Dataset + Ground Truth + Retrieval Eval
Phase 3B  Dense → Learned Sparse → Hybrid/RRF → Reranker → Graph Expansion
Phase 4B  같은 Eval Dataset으로 비교 후 유지·제거 결정
```

Graph Expansion은 Elasticsearch가 graph DB라는 뜻이 아니다. 먼저 기존 관계와 검색 결과를 애플리케이션에서 확장하고, 관계 중심 질문에서 한계가 확인될 때 Neo4j 같은 별도 graph projection을 검토한다.

## 대안과 판단

PostgreSQL + pgvector는 작은 서비스를 단순하게 구성하기에 좋은 대안이고, Qdrant·Weaviate는 vector/hybrid 검색에 강하다. 그러나 이번 포트폴리오에서는 BM25부터 dense·sparse·fusion·reranking까지 한 흐름으로 비교하는 경험이 핵심이다. 기존 프로젝트와의 연속성까지 고려하면 Elasticsearch를 먼저 검증할 이유가 충분하다.

다만 “이전에 사용했다”는 사실만으로 확정하지 않는다. 작은 데이터에 Elasticsearch가 과할 수 있고, 이중 저장과 동기화 비용도 생긴다. 따라서 다음 원칙을 적용한다.

- 기능이 있다는 이유만으로 사용하지 않는다.
- 한 번에 하나의 Retrieval 요소만 추가한다.
- 동일한 Query Dataset과 Ground Truth로 비교한다.
- 품질 향상이 비용과 복잡성을 정당화할 때만 유지한다.

## 결론

Elasticsearch는 과거 기술을 관성적으로 유지하는 선택이 아니라, **해커톤의 기술적 맥락을 이어가면서 Retrieval을 Eval 기반으로 진화시키는 가설**이다. Phase 4B 결과가 이 가설의 채택 또는 폐기를 결정한다.

## 근거

- [Elasticsearch ranking and reranking](https://www.elastic.co/docs/solutions/search/ranking)
- [Elasticsearch sparse vector query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-sparse-vector-query)
- [pgvector hybrid search](https://github.com/pgvector/pgvector)
