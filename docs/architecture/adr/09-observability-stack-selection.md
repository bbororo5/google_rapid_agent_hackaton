# [ADR-0017] GCP 이후 로컬/무료 관찰성 스택 후보 선정

- **상태(Status):** 초안(Draft)
- **날짜(Date):** 2026년 7월 1일

## 배경

GCP를 쓰지 않으므로 Google Cloud Operations도 사용할 수 없다.

Java/Python 내부에는 이미 관찰성 계층이 있다. 이제 결정할 것은 logs, metrics, traces를 로컬에서 어떤 스택으로 모아 볼 것인가다.

Phoenix/OpenInference는 evaluation과 agent trace detail 축으로 유지한다. 이 ADR은 전통 관찰성 3축만 다룬다.

## 요구사항

- Java/Python 로그를 같은 요청으로 검색할 수 있어야 한다.
- latency, error, retry 같은 metrics를 볼 수 있어야 한다.
- Java -> Python -> Java relay 흐름을 trace로 따라갈 수 있어야 한다.
- Docker Compose에서 실행 가능해야 한다.
- Mac/Windows 16GB 환경에서 과도하게 무겁지 않아야 한다.
- 제품급 포트폴리오로 설명 가능한 표준 구성이어야 한다.

## 선택지

아래 선택지는 모두 logs, metrics, traces 3축을 만족할 수 있는 후보만 남긴다. Prometheus 단독, Loki 단독, Prometheus + Loki + Grafana처럼 traces가 빠지는 조합은 후보에서 제외한다.

| 선택지 | 판단 |
|---|---|
| Grafana LGTM | Loki, Prometheus 계열, Tempo, Grafana로 3축을 모두 다룬다. |
| OTel Collector + Grafana LGTM | 앱은 OTLP로 Collector에 보내고, Collector가 LGTM backend로 라우팅한다. 가장 표준적이지만 설정이 더 많다. |
| Elastic Observability | 3축을 통합할 수 있지만, 현재 evidence/business Elasticsearch와 역할 경계가 섞일 수 있다. |
| SigNoz | OpenTelemetry 기반 올인원으로 3축을 다룰 수 있지만, 별도 제품 의존이 커진다. |

## 초안 결정

1차 후보는 **Grafana LGTM stack**으로 둔다.

- Logs: Loki
- Metrics: Prometheus 계열
- Traces: Tempo
- UI: Grafana

OTel Collector는 초기 필수로 두지 않는다. Java/Python telemetry를 여러 backend로 라우팅해야 할 필요가 확인되면 추가 검토한다.

## 이유

부분 조합은 3축 요구사항을 만족하지 못하므로 후보에서 제외한다.

Grafana LGTM은 3축을 모두 충족하고, Docker Compose 기반 제품급 포트폴리오로 설명하기 좋다.

다만 바로 구현을 지시하지 않는다. 먼저 현재 logs/metrics/traces sample을 확인하고, 부족한 부분을 코드로 보강한 뒤 stack 추가 PR로 진행한다.

## 결과

- 관찰성 스택 1차 후보는 Grafana LGTM이다.
- OTel Collector는 후속 확장 선택지로 남긴다.
- Phoenix/OpenInference는 service observability가 아니라 evaluation/agent trace detail 축으로 유지한다.
