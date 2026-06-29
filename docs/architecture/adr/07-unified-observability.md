# [ADR-0015] Java Backend와 Python Agent Core 통합 4축 관찰성 baseline

- **상태(Status):** 제안됨(Proposed)
- **날짜(Date):** 2026년 6월 22일
- **컨텍스트:** LaunchPilot 제품급 최적화, Java Spring Boot Backend, Python FastAPI Agent Core, Google Cloud Operations, OpenTelemetry, OpenInference, Phoenix/Arize, Elastic/Elasticsearch

## 1. 배경과 문제 정의

LaunchPilot은 해커톤 데모 단계를 넘어 제품급 안정화와 성능 개선 단계로 이동하고 있다. 다음 최적화는 추측 기반으로 진행하지 않고, Java Backend와 Python Agent Core를 가로지르는 관찰성 baseline 위에서 수행해야 한다.

AI Agent 제품의 관찰성은 일반적인 서비스 관찰성 3축인 logs, metrics, traces만으로 충분하지 않다. 응답이 빠르고 에러가 없어도 agent output이 근거 없거나 실행 불가능하거나 reviewer/eval 기준을 통과하지 못하면 제품적으로 실패한 응답이다. 따라서 LaunchPilot의 관찰성 baseline은 logs, metrics, traces, evals의 4축으로 본다.

현재 Python Agent Core에는 OpenInference/Phoenix 기반 agent trace와 reviewer/evaluator 흐름이 일부 존재한다. 즉 eval 및 agent trace detail 축은 이미 방향이 잡혀 있다. 그러나 Java Backend와 Python service 전반을 가로지르는 logs, metrics, traces는 아직 제품급 최적화와 회귀 분석에 충분하지 않다.

이 ADR은 기존 eval 축을 대체하거나 재설계하지 않는다. 부족한 logs, metrics, traces를 Java Backend와 Python Agent Core 전반에 보강하고, 네 축이 같은 request, thread, trace 기준으로 연결되도록 통합 관찰성 baseline을 정의한다.

## 2. 현재 관찰성 현황

### 2.1 Python Agent Core

Python Agent Core는 `PHOENIX_API_KEY`가 설정된 경우 Phoenix exporter를 등록한다. OpenInference span kind를 사용해 agent turn, orchestrator pipeline, evidence retrieval, reviewer gate, evaluator 등을 trace로 남긴다.

현재 Python 관찰성은 AI 실행 경로와 품질 평가 흐름을 보는 데 강하다.

- LLM, tool, reviewer, evaluator span을 볼 수 있다.
- OpenInference semantic convention을 따른다.
- Phoenix/Arize 기반 self-reflection과 연결된다.
- tracing 설정이 없어도 no-op으로 동작해 런타임을 깨지 않는다.

다만 이는 Python Agent Core 전체의 service-level 관찰성이 아니다. FastAPI endpoint latency, process/runtime metrics, WebSocket 상태, retry/error rate, queue/backpressure, structured logs 같은 운영 3축은 별도 보강이 필요하다.

### 2.2 Java Backend

Java Backend는 Spring Boot 기반 gateway이자 business persistence owner다.

Java는 다음 흐름의 핵심 경계다.

- CSV upload/import
- `content_posts` 및 `campaigns` Elastic write
- Frontend-facing WebSocket stream
- Python Agent Core로 user turn forwarding
- Python stream block relay
- approval/reject/cancel action 처리
- 승인된 `growth_briefs`, `calendar_events` Elastic write

하지만 현재 Java에는 Actuator, Micrometer, OpenTelemetry, structured logging 같은 제품급 관찰성 설정이 부족하다.

### 2.3 현재 단절 지점

현재 구조에서는 Python agent trace와 Java gateway 동작이 같은 요청 단위로 자연스럽게 이어지지 않는다.

특히 다음 질문에 답하기 어렵다.

- 한 user turn의 end-to-end latency 중 Java, Python, Elastic, LLM/tool 중 어디가 느렸는가?
- CSV import 실패와 agent reasoning 실패를 어떻게 구분하는가?
- approval 실패가 Java validation 문제인지 Elastic write 문제인지 어떻게 확인하는가?
- WebSocket stream이 끊겼을 때 Java relay 문제인지 Python stream 문제인지 어떻게 구분하는가?
- Python Phoenix trace와 Java log를 어떤 식별자로 함께 검색하는가?
- Java가 Python에 전달한 turn과 Python의 `launchpilot.thread` trace를 어떻게 연결하는가?
- 최적화 전후 개선 효과와 eval quality regression을 어떤 기준으로 비교하는가?

## 3. 요구사항 및 제약사항

### 3.1 제품 및 엔지니어링 요구사항

- LaunchPilot의 관찰성 baseline은 logs, metrics, traces, evals의 4축으로 정의한다.
- 기존 Python Agent Core의 OpenInference/Phoenix 기반 eval 및 agent trace detail 축은 유지한다.
- Java Backend와 Python Agent Core 전반에 부족한 logs, metrics, traces를 보강해야 한다.
- 한 user turn의 latency를 Java, Python, Elastic, LLM/tool 구간별로 분해할 수 있어야 한다.
- 최적화 전후에 latency, error, retry, external I/O, token/cost, eval quality를 같은 기준으로 비교할 수 있어야 한다.
- latency를 줄이는 최적화가 evidence grounding, reviewer pass rate, experiment quality를 훼손하지 않았는지 확인할 수 있어야 한다.
- 운영자와 개발자가 `thread_id`, `request_id`, `trace_id`, `workspace_id`, `campaign_id` 중 하나로 관련 logs, traces, eval 결과를 찾을 수 있어야 한다.
- 관찰성 데이터는 raw prompt, raw CSV, credential을 포함하지 않고도 장애 분석과 성능 최적화에 충분해야 한다.

### 3.2 기술 제약사항

- **C1. 4축 baseline 우선:** 최적화는 logs, metrics, traces, evals가 연결된 baseline 위에서 수행한다. latency만 줄이고 eval 품질을 잃는 최적화는 성공으로 보지 않는다.
- **C2. 기존 eval 축 보존:** Python Agent Core의 OpenInference/Phoenix 기반 reviewer/evaluator/self-reflection 흐름은 유지한다. 이 ADR은 eval rubric이나 reviewer gate를 재설계하지 않는다.
- **C3. 부족한 3축 보강:** Java Backend와 Python service 전반의 logs, metrics, traces를 제품급 최적화와 회귀 분석에 충분한 수준으로 보강한다.
- **C4. 추가 운영 컴포넌트 부담 최소화:** 초기 제품화 단계에서는 OpenTelemetry Collector, Grafana stack, 별도 observability cluster 같은 추가 컴포넌트 운영을 피한다.
- **C5. Elastic 비용 및 역할 확대 방지:** Elastic/Elasticsearch는 evidence/business search 역할로 제한한다. Elastic Cloud 비용과 종속성 제약 때문에 Elastic Observability를 통합 관찰성 backend로 추가 채택하지 않는다.
- **C6. 표준 기반 계측:** service telemetry는 OpenTelemetry 표준을 따른다. AI/eval semantic은 기존 OpenInference convention을 유지한다.
- **C7. End-to-end correlation 필수:** Java와 Python의 logs/traces/metrics/evals는 `thread_id`, `request_id`, `trace_id`, `workspace_id`, `campaign_id` 같은 공통 식별자로 연결 가능해야 한다.
- **C8. 관찰성은 비즈니스 흐름을 깨지 않아야 함:** telemetry exporter나 backend 장애가 CSV import, approval persistence, agent turn 처리 자체를 실패시키면 안 된다. 관찰성은 best-effort이며 실패 시 degrade/no-op 되어야 한다.
- **C9. 데이터 최소화와 redaction:** raw CSV, raw prompt, raw Gemini response, credentials, authorization headers, provider-private payload, raw MCP transport message는 logs/traces/evals에 저장하지 않는다.
- **C10. Contract-first 경계 존중:** Java-Python trace propagation을 추가하더라도 기존 conversation-first API 의미를 깨지 않는다. 필요한 경우 `traceparent` header 또는 `trace_context` 필드를 계약에 맞춰 정렬하되 agent business payload와 telemetry payload를 섞지 않는다.

## 4. 기술 선택지

### 4.1 평가 기준

선택지는 다음 기준으로 평가한다.

- 4축 관찰성(logs, metrics, traces, evals)을 한 request/thread 기준으로 연결할 수 있는가.
- 최적화 전후 latency, external I/O, retry, cost, eval quality를 비교할 수 있는가.
- 기존 Python OpenInference/Phoenix eval 축을 보존할 수 있는가.
- Java Backend와 Python Agent Core 사이 trace context propagation을 지원하는가.
- 추가 운영 컴포넌트 부담이 적은가.
- Elastic Cloud 비용과 vendor 종속성을 확대하지 않는가.
- raw prompt/CSV/credential을 남기지 않는 redaction 정책을 유지할 수 있는가.

### 4.2 Option A: Phoenix/Arize 중심 확장

기존 Phoenix/Arize를 중심으로 Python Agent Core의 eval 및 agent trace detail을 유지하고, Java span도 가능한 범위에서 같은 trace backend로 보내는 방식이다.

장점은 기존 Python 관찰성을 가장 잘 활용하고, LLM/tool/reviewer/evaluator 중심의 최적화 스토리를 만들기 쉽다는 점이다. 하지만 Phoenix/Arize는 service-level logs, metrics, Cloud Run runtime health, Java gateway 운영 관찰성 backend로는 자연스럽지 않다.

따라서 Phoenix/Arize는 eval 및 agent trace detail backend로 유지하되, 4축 baseline 전체를 담당하는 중심 backend로 확장하지 않는다.

### 4.3 Option B: Elastic Observability 중심 통합

Elastic Observability/Kibana를 logs, metrics, traces, eval summary의 통합 화면으로 사용하는 방식이다.

장점은 검색과 dashboard가 강하고, `thread_id`나 `campaign_id` 기반 탐색에 유리하다는 점이다. 하지만 Elastic/Elasticsearch는 이미 evidence/business search 역할을 갖고 있고, Elastic Cloud 비용과 종속성 제약이 있다. Observability까지 Elastic에 얹으면 business/evidence/observability 역할이 커지고, Phoenix/Arize의 detailed OpenInference/eval 흐름도 별도로 유지해야 한다.

따라서 Elastic Observability는 초기 채택안에서 제외한다. Elastic/Elasticsearch는 evidence/business search 역할로 제한한다.

### 4.4 Option C: Google Cloud Operations 중심 통합

Google Cloud Logging, Cloud Monitoring, Cloud Trace를 logs, metrics, traces의 1차 backend로 사용하는 방식이다.

장점은 Cloud Run/GCP 배포와 자연스럽게 맞고, 추가 운영 컴포넌트 없이 request logs, service metrics, error, trace를 제품 환경에서 볼 수 있다는 점이다. Elastic Observability 비용과 역할 확대를 피하면서도 Java/Python service-level 3축을 구축할 수 있다.

단점은 Phoenix/Arize처럼 OpenInference/eval detail을 풍부하게 보여주지는 못한다는 점이다. 따라서 eval 및 agent trace detail은 기존 Phoenix/Arize에 남기고, GCP는 service-level logs/metrics/traces의 1차 backend로 사용한다.

### 4.5 Option D: OpenTelemetry Collector 중심 라우팅

Java/Python telemetry를 OpenTelemetry Collector로 보내고, Collector가 Phoenix/Arize, GCP, 기타 backend로 라우팅하는 방식이다.

장점은 vendor-neutral하고 장기 확장성이 높다는 점이다. 하지만 초기 단계에서 Collector 자체가 추가 운영 컴포넌트가 되며, 현재 목표인 최적화 baseline 구축에 비해 운영 부담이 크다.

따라서 Collector는 초기 채택안에서 제외한다. 단, Java/Python 계측은 OpenTelemetry 표준을 따라 향후 Collector 도입이 가능하도록 유지한다.

## 5. 트레이드오프 분석

| 기준 | Phoenix/Arize 중심 | Elastic Observability 중심 | Google Cloud Operations 중심 | OTel Collector 중심 |
|---|---|---|---|---|
| 4축 baseline 적합성 | eval/detail 강함, service 3축 약함 | 통합 화면 강함, eval detail 별도 필요 | service 3축 강함, eval detail 별도 유지 | 라우팅 유연성 강함, 직접 화면 없음 |
| 최적화 전후 비교 | LLM/tool/reviewer 분석 강함 | dashboard 구성 강함 | service latency/error 비교 강함 | backend 조합에 따라 강함 |
| 기존 eval/OpenInference 보존 | 가장 좋음 | 별도 유지 필요 | 별도 유지 필요 | Phoenix 라우팅 가능 |
| Java/Python correlation | OTel 보강 필요 | OTel/APM 보강 필요 | OTel 보강 필요 | 가장 자연스러움 |
| 추가 운영 컴포넌트 부담 | 낮음 | 중간 | 낮음 | 중간~높음 |
| 비용 및 종속성 | Phoenix 비용/종속성 | Elastic 비용/역할 확대 | GCP 배포와 비용 통합 | backend와 Collector 운영 비용 |
| 데이터 최소화/redaction | AI payload 주의 필요 | index 분리 필요 | log/trace redaction 필요 | processor 정책 필요 |

결론적으로, 현재 제약에서는 Google Cloud Operations가 부족한 service-level logs/metrics/traces를 가장 낮은 운영 부담으로 보강한다. Phoenix/Arize는 eval 및 agent trace detail에 강하므로 유지한다. Elastic Observability와 OTel Collector는 장기 선택지로는 가능하지만, 초기 baseline 구축 목적과 비용/운영 부담 제약에는 맞지 않는다.

## 6. 결정

Google Cloud Operations + Phoenix/Arize 이원 구조를 채택한다.

LaunchPilot은 logs, metrics, traces, evals의 4축 관찰성 baseline을 기준으로 최적화와 회귀 분석을 수행한다.

- Logs, metrics, traces는 Google Cloud Logging, Cloud Monitoring, Cloud Trace를 1차 backend로 사용한다.
- Evals 및 agent trace detail은 기존 Phoenix/Arize + OpenInference 축을 유지한다.
- OpenTelemetry는 service telemetry와 trace context propagation의 표준으로 사용한다.
- OpenInference는 AI/eval semantic convention으로 유지한다.
- 초기 제품화 단계에서는 OpenTelemetry Collector, Elastic Observability, Grafana stack을 도입하지 않는다.
- Elastic/Elasticsearch는 evidence/business search 역할로 제한한다.

이 결정은 상시 운영용 통합 모니터링 플랫폼을 완성하는 결정이 아니다. 제품급 최적화와 회귀 분석에 필요한 4축 baseline을 먼저 만들고, 이후 필요가 확인되면 Collector나 별도 dashboard를 추가한다.

## 7. 채택 설계

### 7.1 Java Backend

Java Backend는 Spring Boot 표준 관찰성 계층을 사용해 service-level telemetry를 보강한다.

- Spring Boot Actuator와 Micrometer로 HTTP 및 JVM/service metrics를 노출한다.
- OpenTelemetry instrumentation으로 HTTP request, CSV import, Elastic write, Python turn submit, WebSocket relay, approval persistence span을 남긴다.
- structured logging 또는 MDC를 사용해 `thread_id`, `request_id`, `trace_id`, `workspace_id`, `campaign_id`를 log에 붙인다.
- Cloud Run/GCP 환경에서는 Cloud Logging, Cloud Monitoring, Cloud Trace로 수집되도록 한다.

### 7.2 Python Agent Core

Python Agent Core는 기존 OpenInference/Phoenix 흐름을 유지하면서 service-level 3축을 보강한다.

- 기존 LLM/tool/reviewer/evaluator span은 Phoenix/Arize에 남긴다.
- FastAPI endpoint, turn processing, stream handling, Elastic evidence read, Redis/runtime repository 경계의 logs/traces/metrics를 보강한다.
- Cloud Logging에서 검색 가능하도록 Java와 같은 correlation attributes를 사용한다.
- eval 축은 reviewer/evaluator 결과와 Phoenix/Arize trace detail을 계속 source로 삼는다.

### 7.3 Java -> Python trace context propagation

Java는 Python Agent Core로 user turn을 전달할 때 trace context를 전달해야 한다.

우선 후보는 W3C `traceparent`/`tracestate` header 전파다. 현재 internal contract의 `trace_context` 필드는 request id와 trace id 연결에 사용할 수 있으나, 표준 OTel propagation과 중복되거나 어긋나지 않도록 후속 contract/implementation PR에서 정렬한다.

### 7.4 공통 correlation attributes

네 축은 최소한 다음 식별자로 연결되어야 한다.

- `thread_id`
- `request_id`
- `trace_id`
- `workspace_id`
- `campaign_id`
- `component`
- `operation`
- `status`

Python agent phase나 tool call이 있는 경우 다음 속성을 추가한다.

- `agent.phase`
- `agent.stage`
- `tool.name`
- `validator_passed`
- `eval.score`, eval 점수가 있을 경우

### 7.5 Redaction 정책

관찰성 데이터에는 문제 분석과 최적화에 필요한 식별자와 요약값만 남긴다.

- CSV import는 row count, column names, file size, duration, indexed/failed count만 기록한다.
- LLM 호출은 model name, latency, token/cost summary, reviewer/eval result, redacted input/output summary만 기록한다.
- Evidence retrieval은 evidence ref id, document count, latency를 기록하되 raw document body는 저장하지 않는다.
- API key, authorization header, raw prompt, raw CSV, raw Gemini response, provider-private payload, raw MCP transport message는 저장하지 않는다.

## 8. 결과와 포기하는 것

### 기대 결과

- Java와 Python을 한 request/thread 흐름으로 추적할 수 있다.
- agent latency와 gateway/persistence latency를 구분할 수 있다.
- 최적화 전후 성능 개선을 같은 baseline으로 비교할 수 있다.
- latency 개선이 eval 품질을 훼손하지 않았는지 확인할 수 있다.
- 기존 Phoenix/Arize eval 및 agent trace detail 축을 유지한다.
- Elastic Cloud 비용과 observability 역할 확대를 피한다.
- Collector나 별도 observability stack 운영 부담 없이 GCP-native 경로를 우선 사용한다.

### 포기하는 것

- 당장 하나의 통합 UI에서 4축 전체를 완벽하게 보는 경험은 포기한다.
- Elastic Observability 중심의 통합 dashboard는 초기 채택하지 않는다.
- OpenTelemetry Collector 기반의 장기 라우팅 유연성은 초기부터 운영하지 않는다.
- alerting, SLO, retention 정책은 후속 운영 단계로 남긴다.

## 9. 후속 작업

- Java Backend 최소 관찰성 구현 PR
- Python service-level 관찰성 보강 PR
- Java -> Python trace context propagation PR
- GCP 기반 dashboard, log query, latency breakdown 정리
- 최적화 전후 분석 문서 작성
- `contracts/06-observability`와 Java/Python service-level telemetry 관계 정리

