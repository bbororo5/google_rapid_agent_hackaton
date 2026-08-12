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

각 기능 모듈 안에서 Contract → application → domain/port 방향으로 책임을 구현한다. PostgreSQL·Elasticsearch·외부 API는 해당 모듈의 Port를 구현하고, 구체 객체 조립은 `bootstrap`만 담당한다. Port는 외부 시스템 경계와 모듈 협력 역할에만 만들며 내부 계산까지 추상화하지 않는다.

## Collaboration messages

기능 모듈은 상대 모듈의 구현이나 포괄적인 export 파일을 참조하지 않는다. `contracts/access.py`, `contracts/retrieval.py`, `contracts/bindings.py`처럼 책임 이름이 드러나는 전문 계약만 사용한다.

| 호출자 | 전달 메시지 | 수신 모듈 | 응답 |
| --- | --- | --- | --- |
| HTTP 접근 제어 | 사용자·Campaign 식별자 | `campaigns` | 권한이 확인된 `CampaignScope` |
| `analysis` | `CampaignMetricQuery` | `performance` | 수치와 출처를 담은 `CampaignPerformance` |
| `analysis` | 문서 검색·원문 확인 요청 | `knowledge` | `TextSearchHit`·`CampaignDocument` |
| `performance` | Campaign binding 조회 | `campaigns` | `ExternalCampaignBinding` 목록 |
| `performance` | 연결 자격 증명 요청 | `identity` 구현체 | 만료가 처리된 `PlatformAccess` |
| 광고 연결 API | 계정·Campaign 탐색 Query | `performance` | `ExternalAccount`·`ExternalCampaign` |

`analysis`가 요구하는 정형·문서 검색은 소비자 소유 Port로 한 번 더 좁힌다. 따라서 LangGraph는 `StructuredRetrievalService`나 `TextRetrievalService`의 구체 타입을 알지 않는다. `bootstrap`은 유일한 composition root이므로 각 모듈의 Adapter를 직접 import할 수 있다.

```text
contracts/<capability>.py  Command·Query·Result·역할 Protocol
application/              계약을 수행하는 유스케이스 구현
models.py                 모듈 내부 도메인 상태와 규칙
ports.py                  저장소 등 내부 구현 경계
adapters/·postgres.py     외부 시스템 Adapter
api.py                    HTTP 전달 Adapter
```

`public.py`는 사용하지 않는다. 하나의 공개 출구에 무관한 책임이 다시 모이고 인터페이스 설계가 구현 이후의 export 정리로 퇴행하는 것을 방지하기 위해서다.

컴포넌트는 구체 협력자의 클래스가 아니라 자신에게 필요한 역할을 생성자에서 요구한다. 예를 들어 Campaign 접근은 `CampaignReader`, 데이터 수집은 `ObservationRecorder`, 토큰 갱신은 `GoogleTokenLifecycle`에 의존한다. Command·Query·Result와 순수 도메인 값은 협력자가 아니므로 불필요한 인터페이스로 감싸지 않는다. 실제 역할 구현의 선택은 `bootstrap/wiring.py`에서만 수행한다.

## Constraints

- API가 PostgreSQL 구현을 직접 호출하지 않는다.
- application은 FastAPI, Elasticsearch와 exporter를 알지 않는다.
- 모듈 간 호출은 책임별 `contracts`를 통한다.
- 내부 컴포넌트 간 협력도 역할 Protocol을 통한다.
- Command·Query·Result·도메인 값은 인터페이스화하지 않는다.
- 기능 간 내부 파일 직접 import는 아키텍처 테스트가 차단한다.
- 리팩터링 중 기존 동작과 API 계약을 바꾸지 않는다.
- 구조 규칙은 자동 테스트로 고정한다.

현재 패키지 안내와 실행 방법은 [LaunchPilot API README](../../../services/launchpilot-api/README.md)에서 확인한다.
