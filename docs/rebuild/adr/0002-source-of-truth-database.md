# ADR-0002: PostgreSQL을 배포 기준 Source of Truth로 사용한다

> 상태: **채택 — Phase 3A 전에 전환**
>
> 결정일: 2026-08-10

## 맥락

SQLite는 별도 DB 서버 없이 Phase 1의 도메인 모델과 Phase 2의 OAuth·데이터 수집을 빠르게 검증하기 위해 선택했다. 이 목적에는 충분했지만, 최종 배포 환경의 요구까지 검토한 결정은 아니었다.

LaunchPilot은 Workspace 기반 다중 사용자, OAuth token 갱신, CampaignObservation 저장과 Elasticsearch 검색 Projection을 다룬다. 여러 애플리케이션 인스턴스와 쓰기가 생길 수 있는 서버 환경에서 SQLite는 하나의 DB 파일과 단일 동시 writer라는 제약이 있다.

## 후보 비교

| 후보 | 장점 | 한계 |
| --- | --- | --- |
| SQLite + Elasticsearch | 현재 구현을 유지하며 로컬 실행이 가장 단순함 | 다중 인스턴스·동시 쓰기·접근 제어·백업 운영에 제약이 있음 |
| PostgreSQL + Elasticsearch | 관계형 원본과 검색 Projection의 책임이 명확하고 일반적인 서버 배포에 적합함 | DB 서버와 Projection 동기화를 관리해야 함 |
| PostgreSQL + pgvector | 한 저장소로 단순화할 수 있음 | 계획한 BM25·sparse·fusion·reranker 실험에 추가 조립이 필요함 |
| Elasticsearch만 사용 | 저장소 수가 하나임 | 인증·소유권·정량 원본과 트랜잭션 경계를 검색 인덱스에 맡기게 됨 |

## 결정

- PostgreSQL을 배포 환경의 source of truth로 사용한다.
- SQLite는 Phase 1·2의 검증 구현으로 간주하고 배포 저장소에서는 제외한다.
- Structured Retrieval은 PostgreSQL에서 수행한다.
- Elasticsearch에는 검색에 필요한 파생 문서만 Projection하며 원본으로 사용하지 않는다.

이 선택은 예상 트래픽 규모 때문만이 아니다. 서버형 배포, 다중 사용자 데이터의 무결성, 명시적인 DB 접근 제어와 검색 인덱스 재생성 경계를 설명하기 위한 결정이다.

## 복잡성 제한

포트폴리오에서는 PostgreSQL 단일 인스턴스와 명시적으로 재실행 가능한 projector까지만 구현한다. 고가용성, read replica, Kafka, CDC와 자동 failover는 범위에 포함하지 않는다.

## 관련 문서

- [Retrieval Evolution Plan](../retrieval-evolution-plan.md)
- [ADR-0001 — Elasticsearch 검색 저장소](0001-retrieval-storage-strategy.md)
- [Phase 1 — Domain Model](../phase-1-domain-model.md)

## 근거

- [SQLite — Appropriate Uses](https://www.sqlite.org/whentouse.html)
- [PostgreSQL — Concurrency Control](https://www.postgresql.org/docs/current/mvcc.html)
- [PostgreSQL — Backup and Restore](https://www.postgresql.org/docs/current/backup.html)
