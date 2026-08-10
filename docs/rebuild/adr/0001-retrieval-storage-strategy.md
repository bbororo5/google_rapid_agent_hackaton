# ADR-0001: Elasticsearch를 Retrieval 검색 저장소 후보로 둔다

> 상태: **시험 채택 — Retrieval Eval로 최종 판단**
>
> 결정일: 2026-08-10

## 맥락

[Retrieval Evolution Plan](../retrieval-evolution-plan.md)은 관계형 Structured Retrieval과 BM25를 기준선으로 삼고, dense·sparse·hybrid·reranker를 Eval로 확장한다.

아카이브한 Google ADK 해커톤 프로젝트도 Elasticsearch를 사용했다. 리빌딩은 기존 구현을 그대로 옮기지 않지만, 당시 선택을 현재 데이터와 평가 계획에 맞춰 다시 검증하면 기술적 흐름을 자연스럽게 이어갈 수 있다.

## 후보 비교

| 후보 | 강점 | 이번 결정의 한계 |
| --- | --- | --- |
| PostgreSQL + pgvector | 정형 조회와 관계를 한 원본에 두기 가장 단순함 | BM25부터 sparse·fusion·reranker까지 더 많은 조립이 필요함 |
| Elasticsearch | BM25, dense·sparse, RRF, reranker와 rank evaluation을 한 검색 엔진에서 실험 가능 | 작은 데이터에는 무겁고 명시적 관계 탐색에는 약함 |
| OpenSearch | 유사한 검색 기능, Search Relevance Workbench, Apache 2.0 | 기존 Elasticsearch 경험과의 연속성이 약함 |
| Neo4j | 명시적 관계와 경로 탐색에 가장 강함 | 현재 텍스트 Retrieval 실험 범위와 정량 원본에 과함 |
| Qdrant·Weaviate | vector·hybrid 검색에 강함 | 별도 정량 원본이 필요하고 관계 탐색이 제한적임 |

세 Retrieval을 같은 수준으로 잘하는 단일 DB는 없다. 이번 포트폴리오에서는 단일 저장소보다 각 데이터의 정답 조건에 맞는 역할 분리를 선택한다.

## 결정

- PostgreSQL을 수치·도메인 데이터의 source of truth로 사용한다.
- Elasticsearch를 재생성 가능한 검색 Projection의 주요 후보로 시험 채택한다.
- 관계 탐색은 원본의 명시적 관계로 시작하고, Eval이 필요성을 보일 때만 Neo4j를 검토한다.
- Elasticsearch 최종 채택과 고급 검색 방식은 동일한 Eval Dataset의 결과로 결정한다.

이 선택은 “해커톤에서도 사용했다”는 관성이 아니다. 기존 경험을 출발점으로 삼되, Retrieval 품질 개선이 이중 저장과 운영 비용을 정당화하는지 다시 증명하는 결정이다. OpenSearch는 Elasticsearch의 가장 강한 대안으로 남긴다.

## 관련 문서

- [Retrieval Evolution Plan](../retrieval-evolution-plan.md)
- [ADR-0002 — PostgreSQL Source of Truth](0002-source-of-truth-database.md)
- [Phase 0 — Product & Evaluation Charter](../phase-0-decision-charter.md)
- [Phase 1 — Domain Model](../phase-1-domain-model.md)
- [Archived Google ADK prototype — Elasticsearch context](../../../archive/google-adk-hackathon-prototype/apps/agent/README.md)

## 근거

- [Elasticsearch ranking evaluation](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-rank-eval)
- [OpenSearch hybrid search optimization](https://docs.opensearch.org/latest/search-plugins/search-relevance/optimize-hybrid-search/)
- [pgvector hybrid search](https://github.com/pgvector/pgvector)
- [Neo4j semantic indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/)
