# Current Rebuild Design

이 디렉터리는 LaunchPilot 리빌드의 제품·도메인·아키텍처 결정을 관리한다. 전체 문서 탐색과 현재 로드맵은 상위 [문서 포털](../README.md)에서 시작한다. 아카이브 문서와 충돌하면 이 디렉터리의 확정 결정이 우선한다.

## Documents

| Phase | 문서 | 결정 상태 | 구현 진척도 |
| --- | --- | --- | --- |
| Phase 0 | [`phase-0-decision-charter.md`](phase-0-decision-charter.md) | 확정 | 완료 |
| Phase 1 | [`phase-1-domain-model.md`](phase-1-domain-model.md) | 확정 | 완료 |
| Phase 2 | [`phase-2-multiplatform-ingestion.md`](phase-2-multiplatform-ingestion.md) | 확정 | 세 플랫폼 mock E2E 완료, 실제 Ads 성과 검증 대기 |
| Phase 3A~4B | [`retrieval-evolution-plan.md`](retrieval-evolution-plan.md) | 확정 | 3A 완료, 4A Dataset 작성 기반 완료·협업 검수 대기 |

## Architecture Decision Records

| ADR | 결정 | 상태 |
| --- | --- | --- |
| ADR-0001 | [`Elasticsearch를 Retrieval 검색 저장소 후보로 둔다`](adr/0001-retrieval-storage-strategy.md) | 시험 채택, Retrieval Eval로 최종 판단 |
| ADR-0002 | [`PostgreSQL을 배포 기준 Source of Truth로 사용한다`](adr/0002-source-of-truth-database.md) | 채택·구현 완료 |

## Status rule

- **논의 중:** 현재 작업 모델이며 사용자와 의미·범위를 조정할 수 있다.
- **확정:** 다음 Phase의 입력으로 사용할 수 있는 결정이다.
- 구현 진척도는 결정 상태와 별도로 기록한다.
- 확정 전 후보 엔티티를 API·DB 계약이나 구현 코드로 먼저 고정하지 않는다.

## Boundary

- 이곳에는 제품·설계의 **무엇과 왜**만 기록한다.
- 실행 명령과 환경변수는 [서비스 README](../../services/launchpilot-api/README.md)에서 관리한다.
- Golden Dataset 작성법은 [Eval README](../../services/launchpilot-api/evals/README.md)에서 관리한다.
- 더 이상 유효하지 않은 설계는 [`archive/`](../../archive/)로 이동한다.
