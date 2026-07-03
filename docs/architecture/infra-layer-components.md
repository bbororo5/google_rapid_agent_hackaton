# 인프라 레이어 컴포넌트 경계

상태: Draft  
날짜: 2026-07-01

## 목적

Python Agent Core의 인프라 레이어를 세 컴포넌트로 고정한다.

이 문서는 후속 specialist agent / orchestrator 작업이 인프라 기능을 어디서 가져와야 하는지 알 수 있도록 경계를 선언한다.

## 컴포넌트

| 컴포넌트 | 현재 디렉터리 | 책임 |
|---|---|---|
| State / Memory | `app/runtime/` | 대화 상태, 상태 전이 확정, runtime repository, Redis state cache, episode memory, restore |
| Observability | `app/infra_observability/`, `app/telemetry/`, `app/tracing/` | logs, metrics, traces, correlation, Java/Python trace 연결, Grafana Alloy export |
| Evaluation | `app/eval/`, `app/phoenix_export/` | evaluation 실행, LLM-as-judge, evaluation report, Phoenix/OpenInference export |

## 경계 원칙

- 컴포넌트는 외부에서 사용할 공개 진입점을 가진다.
- 지금은 디렉터리 이동보다 경계 선언을 우선한다.
- 다른 레이어는 가능하면 컴포넌트의 공개 진입점 또는 README에 명시된 API를 통해 접근한다.
- 인프라 컴포넌트는 agent 협업 구조나 product workflow 결정을 소유하지 않는다.

## State / Memory

State / Memory는 agent core의 현재 상태와 과거 실행 기억을 관리한다.

포함한다:

- `ConversationState`
- 자연어에서 추출된 변경 제안(`ProposedChange`)
- 상태 확정 규칙(`apply_proposed_change`, transitions)
- Redis 기반 state cache
- Elastic/InMemory runtime repository
- runtime artifact
- episode memory
- restore

포함하지 않는다:

- 어떤 전문 에이전트를 호출할지 결정하는 coordinator 정책
- LLM worker prompt
- 품질 평가 점수

## Observability

Observability는 서비스 실행을 logs, metrics, traces로 관찰할 수 있게 한다.

포함한다:

- log correlation
- Java에서 전달된 `request_id`, `trace_id`, `thread_id`, `workspace_id`, `campaign_id`
- OpenTelemetry span/metadata helper
- Grafana Alloy OTLP export

포함하지 않는다:

- evaluation score
- LLM-as-judge
- Phoenix failure reflection의 의사결정 권한

## Evaluation

Evaluation은 agent output 품질을 측정한다.

포함한다:

- scenario dataset
- deterministic metrics
- LLM-as-judge
- evaluation report
- Phoenix/OpenInference export

포함하지 않는다:

- production request의 상태 전이 확정
- 사용자 승인 권한
- 관찰성 3축 backend 선택

## 후속 정리 기준

아래 조건이 생기면 디렉터리 이동 또는 추가 분리를 검토한다.

- import 경계가 계속 새는 경우
- README/public facade로 책임 설명이 부족한 경우
- specialist agent layer가 인프라 내부 모듈에 직접 과하게 의존하는 경우
