# ADR-0002 — PostgreSQL Source of Truth

> 상태: **채택·구현 완료** · 결정일: 2026-08-10

## Context

SQLite는 서버 없이 도메인과 OAuth 수집을 검증하는 데 충분했지만, Workspace 기반 다중 사용자, token 갱신과 여러 서버 인스턴스의 동시 쓰기를 설명할 최종 배포 저장소로는 적합하지 않았다.

## Options

| 후보 | 장점 | 한계 |
| --- | --- | --- |
| SQLite + Elasticsearch | 로컬 구성이 가장 단순 | 동시 쓰기·다중 인스턴스·운영 백업에 제약 |
| PostgreSQL + Elasticsearch | 관계형 원본과 검색 Projection 경계가 명확 | 두 저장소의 Projection 동기화 필요 |
| PostgreSQL + pgvector | 저장소 단순화 | 계획한 검색 실험에 추가 조립 필요 |
| Elasticsearch only | 저장소 하나 | 인증·소유권·정량 트랜잭션을 검색 인덱스에 맡김 |

## Decision

- PostgreSQL을 Campaign, Observation, OAuth control-plane의 Source of Truth로 사용한다.
- Structured Retrieval은 PostgreSQL에서 수행한다.
- Elasticsearch에는 재생성 가능한 검색 문서만 Projection한다.
- SQLite는 초기 검증과 일회성 데이터 이전에만 사용하고 배포 저장소에서 제외한다.

포트폴리오 범위는 PostgreSQL 단일 인스턴스와 재실행 가능한 Projection까지다. 고가용성, replica, Kafka·CDC는 구현하지 않는다. 검색 저장소 선택은 [ADR-0001](0001-retrieval-storage-strategy.md)을 따른다.

## References

- [SQLite Appropriate Uses](https://www.sqlite.org/whentouse.html)
- [PostgreSQL Concurrency Control](https://www.postgresql.org/docs/current/mvcc.html)
