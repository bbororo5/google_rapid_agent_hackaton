# 인프라 레이어 관찰성 3축 프레임

상태: Draft  
날짜: 2026-07-01  
관련 문서: `docs/architecture/adr/07-unified-observability.md`, `backend/OBSERVABILITY.md`

## 목적

GCP 제거 이후 로컬 Docker Compose 환경에서 관찰성 3축을 어떻게 나누어 볼지 선언한다.

이 문서는 전통적 관찰성 3축만 다룬다. Evaluation과 agent output 품질 평가는 별도 문서에서 다룬다.

이 문서는 작업 지시서가 아니다. 후속 코드 보강과 기술 선택을 쪼갤 때 참조할 기준 문서다.

## 기본 입장

관찰성 도구를 먼저 고르지 않는다.

먼저 Java/Python 통합 실행 흐름을 logs, metrics, traces로 어떻게 나누어 볼지 정한다. 그 프레임을 바탕으로 후속 PR에서 코드 보강 단위를 쪼개고, 필요할 때 Prometheus/Grafana/Loki, OTel Collector, Elastic Observability 같은 솔루션을 검토한다.

## 공통 식별자

Java와 Python의 logs, metrics, traces는 같은 사용자 요청으로 묶여야 한다.

| 식별자 | 목적 | 현재 상태 |
|---|---|---|
| `request_id` | 한 사용자 요청 식별 | 구현됨 |
| `trace_id` / `otel_trace_id` | trace 연결 | 구현됨 |
| `thread_id` | 대화 세션 | 구현됨 |
| `workspace_id` | 데이터 경계 | 구현됨 |
| `campaign_id` | 캠페인 작업 범위 | 구현됨 |
| `component` | Java/Python 내부 컴포넌트 | 일부 구현됨 |
| `operation` | 실행 operation | 일부 구현됨 |

## 1. Logs

로그는 "어떤 경계에서 무슨 일이 일어났는가"를 보여야 한다.

| 대상 | 봐야 할 로그 |
|---|---|
| Java API/WebSocket | 요청 수신, 세션 open/close/reject, malformed message |
| Java conversation | `message.send` 처리, action/free-form 분기, duplicate command |
| Java -> Python | turn submit 시작/성공/실패, timeout |
| Python turn | turn accepted/started/finished/failed |
| Python orchestration | reducer decision, delegation mode, phase 실행 결과 |
| Java/Python stream | stream 수신/relay 실패 |
| Elastic/Redis | read/write 실패, conflict, rehydrate |
| approval | approval 검증/저장 성공/실패 |

현재 기반은 다음이다.

- Java: `ObservabilityGateway`, `LoggingObservabilityGateway`
- Python: `CorrelationLogFilter`, `bind_correlation`, `telemetry`

## 2. Metrics

metrics는 "어디가 느리거나 불안정한가"를 보여야 한다.

초기에는 중앙 metrics backend 없이 로그와 trace에 남는 duration/count sample로 본다.

| 지표 | 목적 | 우선순위 |
|---|---|---|
| Java request duration | gateway/API 병목 확인 | 높음 |
| Java -> Python submit latency | 컨테이너 간 호출 병목 확인 | 높음 |
| Python turn duration | agent turn 전체 지연 확인 | 높음 |
| phase duration | phase별 병목 확인 | 높음 |
| Elastic query/write latency | 저장소 병목 확인 | 높음 |
| Redis hit/miss | hot state 효과 확인 | 중간 |
| error count | 실패 구간 확인 | 높음 |
| retry count | 불안정 구간 확인 | 중간 |
| stream relay error count | 응답 유실 확인 | 중간 |

## 3. Traces

trace는 Java와 Python을 하나의 실행 흐름으로 연결해야 한다.

최소 흐름:

```text
Frontend message.send
-> Java conversation
-> Java agentbridge
-> Python turn
-> Python orchestration
-> Python stream
-> Java relay
-> Frontend blocks
```

현재 기반:

- Java가 `traceparent`와 `trace_context`를 만든다.
- Java가 Python 요청 header/body에 correlation 정보를 전달한다.
- Python `AgentTraceContext`가 이를 log/telemetry metadata로 연결한다.

trace 프레임에서 중요한 질문은 다음이다.

- Java에서 생성한 `request_id`가 Python 로그에도 같은 값으로 남는가
- Java `traceparent`의 trace id가 Python `trace_id`로 이어지는가
- Python 내부 비동기 실행 중 trace/correlation이 끊기지 않는가
- Java stream relay와 Python turn이 같은 `thread_id`로 연결되는가

## 관찰성 요구사항

인프라 레이어 관찰성은 아래 요구사항을 만족해야 한다.

| 요구사항 | 핵심 질문 |
|---|---|
| Java boundary | Java gateway와 business persistence 경계에서 시작/성공/실패가 보이는가? |
| Python boundary | Python turn, orchestration, state/memory 경계에서 시작/성공/실패가 보이는가? |
| Cross-container trace | Java -> Python -> Java relay 흐름이 같은 요청으로 연결되는가? |
| Runtime state | Redis/Elastic runtime state 접근과 충돌이 보이는가? |
| Latency sample | 느린 구간을 최소한 duration sample로 구분할 수 있는가? |
| Error/retry sample | 실패와 재시도가 어느 경계에서 발생했는지 구분할 수 있는가? |

후속 코드 보강과 기술 선택은 이 요구사항을 기준으로 판단한다. 이 문서는 어떤 요구사항을 먼저 구현하라고 지시하지 않는다.

## 기술 선택 기준

관찰성 솔루션 도입 여부는 다음 질문에 답하지 못할 때 검토한다.

- 로그만으로 경계별 실패 원인을 찾기 어려운가?
- duration/count sample만으로 병목 비교가 어려운가?
- Java/Python trace 연결을 수동으로 따라가기 어려운가?
- 로컬 개발자가 같은 기준으로 문제를 재현하고 비교하기 어려운가?

이 질문에 실제 gap이 확인되기 전까지는 별도 관찰성 backend 도입을 보류한다.
