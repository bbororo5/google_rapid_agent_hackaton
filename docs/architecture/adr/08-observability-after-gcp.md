# [ADR-008] GCP 제거 이후 관찰성 3축 기준

- **상태(Status):** 제안됨(Proposed)
- **날짜(Date):** 2026년 7월 1일

## 배경

ADR-0015는 Java/Python 서비스 관찰성 3축(logs, metrics, traces)의 1차 backend로 Google Cloud Operations를 선택했다.

하지만 GCP 예산 초과로 Cloud Logging, Cloud Monitoring, Cloud Trace를 사용할 수 없다. 따라서 GCP에 의존하지 않는 로컬 기준이 필요하다.

Phoenix/OpenInference 기반 agent trace와 evaluation은 GCP와 무관하므로 그대로 둔다. 이번 ADR은 전통 관찰성 3축만 다룬다.

## 결정

Google Cloud Operations 채택을 철회한다.

초기 Docker Compose 환경에서는 별도 관찰성 backend를 추가하지 않는다.

- **logs:** Java/Python stdout의 correlated log를 사용한다.
- **traces:** Java가 만든 `traceparent`와 `trace_context`를 Python으로 전파한다.
- **metrics:** 중앙 metrics backend 없이 duration, healthcheck, error/retry count를 log 기반 sample로 본다.

즉 초기 기준은 다음이다.

```text
correlated logs
+ Java -> Python trace context propagation
+ duration/error/retry metric samples
```

## 이유

현재 목표는 GCP 제거 후 로컬 실행 환경을 마련하는 것이다. Prometheus/Grafana/Loki, OTel Collector, Elastic Observability는 모두 가능하지만 지금 바로 넣으면 운영 컴포넌트가 늘어난다.

먼저 Java/Python 실행 흐름이 공통 식별자로 이어지는지 확인하고, 실제 병목이 확인된 뒤 별도 backend 도입을 결정한다.

## 범위 밖

- Phoenix/OpenInference evaluation 재설계
- agent loop 품질 평가 기준 변경
- Prometheus/Grafana/Loki 즉시 도입
- OTel Collector 즉시 도입
- Elastic Observability 도입

## 결과

- ADR-0015의 Google Cloud Operations 결정은 이 ADR로 대체한다.
- Docker Compose에는 관찰성 전용 컨테이너를 추가하지 않는다.
- 후속 작업은 Java/Python correlation field, trace context propagation, duration/error/retry sample 점검이다.
