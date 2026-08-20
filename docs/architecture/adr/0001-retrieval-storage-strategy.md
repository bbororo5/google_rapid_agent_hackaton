# ADR-0001 — Elasticsearch Retrieval Projection

> 상태: **시험 채택 · Eval로 최종 판단** · 결정일: 2026-08-10

## Context

LaunchPilot은 PostgreSQL 정형 조회와 BM25를 Baseline으로 두고 dense·sparse·hybrid·reranker를 같은 Dataset에서 비교한다. 해커톤 프로토타입의 Elasticsearch 경험을 재사용할 수 있지만, 관성만으로 운영 복잡성을 정당화할 수는 없다.

## Options

| 후보 | 장점 | 한계 |
| --- | --- | --- |
| PostgreSQL + pgvector | 원본과 vector를 한곳에 둠 | sparse·fusion·reranker 조립이 늘어남 |
| Elasticsearch | BM25부터 vector·sparse·RRF·reranker까지 한 엔진에서 실험 | 작은 데이터에 무겁고 관계 경로에 약함 |
| OpenSearch | 유사한 검색 기능과 Apache 2.0 | 기존 경험과의 연속성이 낮음 |
| Vector DB (Qdrant·Weaviate) | vector·hybrid에 강함 | 정형 원본이 별도로 필요하고 관계 탐색이 제한됨 |
| Neo4j | 명시적 관계와 경로에 강함 | 현재 텍스트 검색 범위에는 과함 |

## Decision

- PostgreSQL은 도메인·정량 데이터의 Source of Truth로 유지한다.
- Elasticsearch는 재생성 가능한 문서 검색 Projection으로 시험 채택한다.
- 관계는 기존 명시적 참조부터 사용하고 Eval이 필요성을 보일 때만 graph DB를 검토한다.
- 고급 검색은 동일 Golden Dataset에서 품질 개선이 이중 저장 비용을 정당화할 때만 채택한다.

OpenSearch는 가장 가까운 대안이다. 전체 실험 순서는 [Retrieval Evolution](../retrieval-evolution-plan.md), 원본 DB 결정은 [ADR-0002](0002-source-of-truth-database.md)를 따른다.

## References

- [Elasticsearch ranking evaluation](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-rank-eval)
- [OpenSearch hybrid optimization](https://docs.opensearch.org/latest/search-plugins/search-relevance/optimize-hybrid-search/)
- [pgvector hybrid search](https://github.com/pgvector/pgvector)
