# Retrieval Evolution Plan

> 상태: **확정 — 각 고도화 기술은 Eval 후 개별 결정**

## 목적

광고 캠페인을 분석하려면 세 종류의 Retrieval이 필요하다.

| Retrieval | 답해야 하는 질문 | 품질 기준 |
| --- | --- | --- |
| 결정적 정형 조회 | 어떤 지표가 어느 기간·플랫폼에서 변했는가? | 수치·기간·대상의 정확성 |
| 관련도 기반 텍스트 검색 | 이 변화와 관련된 메모·브리프·과거 분석은 무엇인가? | 관련 문서의 검색 순위 |
| 관계 기반 탐색 | 이 주장과 가설은 어떤 근거에서 나왔는가? | 연결 경로와 출처의 추적 가능성 |

한 방식만으로는 세 품질을 보장할 수 없다. 따라서 작은 기준선을 먼저 만들고, 같은 Eval Dataset으로 검증하며 필요한 Retrieval만 추가한다.

## Baseline: Phase 3A

베이스라인은 다음 범위까지만 구현한다.

- **Structured Retrieval:** 관계형 원본에서 ID 직접 조회, 기간·플랫폼 필터와 metric 집계
- **BM25 Retrieval:** 검색 Projection에서 메모·브리프·과거 분석의 lexical 검색
- **Evidence Resolution:** 검색 결과의 `source_ref`가 가리키는 원본 근거 확인

Dense, learned sparse, hybrid, reranker와 graph expansion은 베이스라인에 포함하지 않는다. Evidence의 직접 참조를 확인하는 것은 검증이며, 여러 관계를 확장하는 Graph Retrieval과 구분한다.

## Eval과 확장

| Phase | 작업 | 결정할 것 |
| --- | --- | --- |
| 3A | Structured Retrieval + BM25 | 재현 가능한 기준선 확립 |
| 4A | Query Dataset + Ground Truth | 정형 정확성과 Recall@K·MRR·nDCG@K 측정 기준 확립 |
| 3B | Dense → learned sparse → hybrid/RRF → reranker → graph expansion 실험 | 한 번에 한 요소만 추가 |
| 4B | 동일 Dataset으로 품질·지연·복잡성 비교 | 개선된 구성만 유지하고 나머지는 제거 |

이 순서는 기술이 앞 단계를 대체한다는 뜻이 아니다. Dense와 sparse는 BM25와 다른 검색 신호이고, hybrid는 이들을 결합하며, reranker는 검색된 후보를 다시 정렬한다. Graph expansion은 검색 순위가 아니라 근거 관계를 넓히는 별도 축이다.

## 기술 결정 기록 원칙

고도화 단계마다 구현 전에 가설과 비교 대상을 ADR로 제안하고, Eval 후 상태를 `채택` 또는 `기각`으로 갱신한다. 예정된 결정 대상은 다음과 같다.

- BM25 index·analyzer·문서 단위
- Dense embedding 모델과 vector index
- Learned sparse 모델
- Hybrid fusion 방식
- Reranker 모델과 적용 후보 수
- Graph expansion 방식과 graph DB 필요 여부

## 관련 문서

- [Phase 0 — Product & Evaluation Charter](phase-0-decision-charter.md)
- [Phase 1 — Domain Model](phase-1-domain-model.md)
- [ADR-0001 — Retrieval 검색 저장소 후보](adr/0001-retrieval-storage-strategy.md)
