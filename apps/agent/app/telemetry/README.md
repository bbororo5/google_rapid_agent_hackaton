# telemetry — Observability 도메인 이벤트 facade

LaunchPilot 코드가 관찰성 backend의 세부 용어를 직접 알지 않도록, 제품/도메인 이벤트를 metadata와 span 기록으로 바꾼다.

`telemetry/`는 독립 컴포넌트가 아니라 Observability 컴포넌트의 내부 facade다.

## telemetry와 tracing 차이

| 모듈 | 역할 |
|---|---|
| `telemetry/` | `turn`, `pipeline`, `guardrail`, `episode` 같은 LaunchPilot 의미를 표현 |
| `tracing/` | OpenInference/OpenTelemetry span을 실제로 생성하는 낮은 수준 helper |
| `infra_observability/` | logs/metrics/traces export와 correlation 연결 |

도메인 코드는 가능하면 `tracing.*`를 직접 호출하지 않고 `telemetry.*`를 호출한다.
