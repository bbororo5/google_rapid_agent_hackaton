# infra_observability — Observability 컴포넌트

서비스 실행을 logs, metrics, traces로 관찰할 수 있게 한다.

이 컴포넌트는 "에이전트가 좋은 답을 냈는가"를 판단하지 않는다. 그것은 `eval/`과 `phoenix_export/`가 맡는다.

## 책임

- Java/Python 요청 상관관계 유지
- log record에 `request_id`, `trace_id`, `thread_id`, `workspace_id`, `campaign_id` 부착
- Python service telemetry를 OpenTelemetry로 내보냄
- 로컬 Alloy를 통해 Grafana Cloud로 logs/metrics/traces 전송

## 공개 진입점

| API | 역할 |
|---|---|
| `CorrelationLogFilter` | LaunchPilot log record에 correlation 필드 추가 |
| `bind_correlation(...)` | 현재 async context에 correlation 값 바인딩 |
| `init_infra_observability(trace_provider)` | OTLP exporter를 Alloy endpoint에 연결 |

## 관련 내부 모듈

| 모듈 | 역할 |
|---|---|
| `app.telemetry` | LaunchPilot 도메인 이벤트를 trace metadata/span으로 변환 |
| `app.tracing` | OpenInference/OpenTelemetry span helper |

현재는 내부 모듈을 이동하지 않는다. 인프라 레이어 관점에서는 모두 Observability 컴포넌트에 속한다.
