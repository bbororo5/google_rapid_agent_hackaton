# tracing — Observability 내부 span helper

턴이 처리되는 동안 "무슨 단계에서 무엇이 있었는지"를 추적 기록으로 남긴다.
Phoenix/Arize 같은 도구가 이 기록을 트리로 보여준다.

```
턴 처리 ──▶ tracing.*_span(...)  ── 단계마다 span(구간) 기록
                  │
                  ▼
        OpenTelemetry ──▶ Phoenix/Arize 또는 Grafana Cloud
        (관측 키 없으면 자동으로 아무것도 안 함 = no-op)
```

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [spans.py](spans.py) | 도메인 span 만들기 (체인/에이전트/가드레일/검색 구간) |

## 컴포넌트 경계

`tracing/`은 독립 컴포넌트가 아니라 Observability 컴포넌트의 내부 모듈이다.

- Phoenix provider 등록: [../phoenix_export/](../phoenix_export/)
- Grafana Alloy OTLP export: [../infra_observability/](../infra_observability/)
- 도메인 이벤트 facade: [../telemetry/](../telemetry/)

## 핵심 원칙

- **민감정보 금지.** span에는 간추린 JSON 요약만. 원본 CSV·프롬프트·키 안 넣음.
- **꺼져도 안전.** 관측 키가 없으면 no-op 추적기라 본 흐름에 영향 0.
