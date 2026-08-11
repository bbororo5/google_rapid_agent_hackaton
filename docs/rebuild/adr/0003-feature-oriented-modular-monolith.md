# ADR-0003 — Feature-oriented Modular Monolith

> 상태: **채택 · 구현 완료** · 결정일: 2026-08-11

## Context

초기 Baseline은 `domain/application/api/infrastructure` 계층으로 책임을 분리했다. 의존 방향은 이해하기 쉬웠지만 기능 하나를 변경할 때 여러 최상위 패키지를 오가고, `infrastructure`, `services.py`, `ports.py`, `control_plane.py`처럼 변경 이유가 다른 코드가 모이는 신호가 나타났다.

## Options

| 구조 | 장점 | 한계 |
| --- | --- | --- |
| 계층별 패키지 유지 | 전통적인 의존 방향이 선명함 | 기능 변경이 여러 폴더에 분산됨 |
| 마이크로서비스 분리 | 배포·확장 경계가 강함 | 현재 규모와 포트폴리오 범위에 과함 |
| 기능 모듈 + 내부 계층 | 관련 코드가 모이고 단일 배포를 유지 | 모듈 간 의존 규칙을 명시해야 함 |

## Decision

단일 FastAPI 배포를 유지하면서 코드를 다음 제품 책임으로 나눈다.

```text
bootstrap      실행·설정·객체 조립
identity       로그인·Workspace·플랫폼 권한
campaigns      Campaign·Conversation·외부 Campaign binding
performance    플랫폼 성과 수집·Observation·정형 조회
knowledge      문서 원본·텍스트 Retrieval
analysis       LangGraph·Tool·Evidence·답변
evaluation     Golden Dataset·Eval
observability  OpenTelemetry·OpenInference 전송
devtools       mock 플랫폼 등 로컬 지원 도구
persistence    공유 PostgreSQL 연결·스키마 실행 기반
shared         기능에 종속되지 않는 오류·시간 값
```

각 기능 모듈 안에서 HTTP → application → model/port 방향을 지킨다. PostgreSQL·Elasticsearch·외부 API는 해당 모듈의 Port를 구현하고, 구체 객체 조립은 `bootstrap`만 담당한다. Port는 외부 시스템 경계에만 만들며 내부 계산까지 추상화하지 않는다.

## Constraints

- API가 PostgreSQL 구현을 직접 호출하지 않는다.
- application은 FastAPI, Elasticsearch와 exporter를 알지 않는다.
- 모듈 간 호출은 공개 service·contract를 통한다.
- 리팩터링 중 기존 동작과 API 계약을 바꾸지 않는다.
- 구조 규칙은 자동 테스트로 고정한다.

현재 패키지 안내와 실행 방법은 [LaunchPilot API README](../../../services/launchpilot-api/README.md)에서 확인한다.
