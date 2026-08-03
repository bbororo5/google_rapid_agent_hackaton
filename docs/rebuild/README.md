# Rebuild Documentation

이 디렉터리는 LaunchPilot 리빌드의 현행 결정과 진행 중인 설계를 관리한다. 아카이브 문서와 충돌하면 이 디렉터리의 확정 결정이 우선한다.

## Documents

| Phase | 문서 | 상태 |
| --- | --- | --- |
| Phase 0 | [`phase-0-decision-charter.md`](phase-0-decision-charter.md) | 확정 |
| Phase 1 | [`phase-1-domain-model.md`](phase-1-domain-model.md) | 논의 중 |

## Status rule

- **논의 중:** 현재 작업 모델이다. 사용자와 도메인 의미를 논의하면서 변경할 수 있다.
- **확정:** 다음 Phase의 입력으로 사용할 수 있다.
- 확정 전 후보 엔티티를 API·DB 계약이나 구현 코드로 먼저 고정하지 않는다.

## Phase 1 focus

현재 Phase 1에서는 다음 순서로 도메인 모델을 완성한다.

1. 플랫폼 원본과 비즈니스 모델의 Context 경계
2. 캠페인 단위 Observation 구조
3. `Campaign`의 의미와 생명주기
4. 핵심 Aggregate Root
5. `Signal → Hypothesis → Experiment → Outcome`의 관계와 불변 규칙
6. 전체 도메인 관계도와 면접 방어 논리
