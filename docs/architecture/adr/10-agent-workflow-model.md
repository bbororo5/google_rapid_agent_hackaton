# [ADR-0018] 복합 실무 에이전트를 위한 Collaborative workflow 선정

- **상태(Status):** 초안(Draft)
- **날짜(Date):** 2026년 7월 1일

## 배경

현재 Python Agent Core는 Gemini + Google ADK `LlmAgent(output_schema=...)`를 전제로 만들어졌다.

이 전제에서는 intent 해석, worker 산출물 생성, schema validation을 ADK/Gemini 경계 안에서 처리할 수 있었다.

하지만 ADK 공식 문서상 `output_schema`와 tools를 함께 쓰는 방식은 특정 모델에만 지원된다. 무료 클라우드 LLM을 검토하는 과정에서도 RPM 한도는 NVIDIA NIM 같은 후보로 완화할 수 있었지만, Gemini 수준의 schema 출력 안정성은 그대로 옮겨오지 못했다.

따라서 문제는 특정 provider 선택이 아니라, Gemini 기능에 기대던 workflow 책임을 다시 나누는 것이다.

## 요구사항

- 사용자는 실무 감독자 역할을 가져야 한다.
- 초보 사용자는 사수처럼 개입하는 에이전트 지원을 받을 수 있어야 한다.
- 분석, 전략, 작성, 검증 같은 전문 에이전트가 역할별로 협업해야 한다.
- 자연어 intent 해석은 유지하되, 상태 확정 권한까지 LLM에 맡기지 않아야 한다.
- provider가 바뀌어도 workflow 책임 경계가 유지되어야 한다.

## 선택지

| 선택지 | 판단 |
|---|---|
| Graph-based workflow | 노드와 엣지로 책임과 route를 드러내기 좋다. 단순하고 설명 가능한 흐름에는 적합하지만, 실무자의 자유로운 요청과 전문 에이전트 협업을 중심 모델로 표현하기에는 고정 흐름이 먼저 보인다. |
| Dynamic workflow | 조건, 반복, 병렬, 재시도를 코드로 표현하기 좋다. 복잡한 실행 정책에는 유리하지만, 기본 구조가 코드 안에 숨기 쉬워 팀이 agent 협업 모델을 논의하기 어렵다. |
| Collaborative workflow | coordinator와 specialist agents를 전제로 하므로, 사용자를 감독자로 두고 여러 전문 에이전트가 보조자처럼 협업하는 구조에 가장 가깝다. 다만 coordinator LLM이 상태 확정 권한까지 갖지 않도록 경계가 필요하다. |

## 결정

기본 workflow 모델은 **Collaborative workflow**로 둔다.

이 결정은 agent core를 단일 고정 절차가 아니라, 사용자 감독 아래 여러 전문 에이전트가 협업하는 실행 구조로 본다는 뜻이다.

## 이유

이 프로젝트는 정해진 단계만 순서대로 수행하는 자동화가 아니다. 실제 실무자는 상황에 따라 분석을 더 시키거나, 전략을 건너뛰거나, 초안을 먼저 만들고 다시 검토를 요청할 수 있다.

전문가 사용자에게 에이전트는 보조자이자 실행자여야 한다. 초보 사용자에게는 사수처럼 판단 기준을 제시하고 다음 행동을 안내할 수 있어야 한다.

이 요구에는 Graph-based의 고정 route보다 Collaborative workflow가 더 잘 맞는다. Dynamic workflow는 복잡한 실행 정책을 표현하는 보완 수단으로 유용하지만, 기본 협업 모델을 설명하는 선택지로는 덜 직접적이다.

## 결정 경계와 후속 보완

Collaborative workflow를 선택한다고 해서 coordinator LLM에 모든 권한을 넘기지는 않는다.

협업과 확정 권한은 분리한다.

- Agent/coordinator: 해석, 생성, 제안, 작업 분배
- Policy/reducer: 상태 전이, 승인, 기록, 산출물 확정

이 보완은 Collaborative workflow의 약점을 줄이기 위한 채택 조건이다. 전문 에이전트의 자유도는 유지하되, 실무 결과물의 확정은 사용자 감독과 명시적 규칙 아래 둔다.

Graph-based workflow와 Dynamic workflow는 폐기하지 않는다. 책임 경계를 시각화하거나, 반복/재시도/병렬 실행이 복잡해지는 구간에서 보조적으로 사용할 수 있다.

## 결과

- agent core의 기본 모델은 Collaborative workflow로 검토한다.
- Gemini `output_schema`에 기대던 책임은 agent 협업 구조와 policy/reducer 경계로 재배치한다.
- 후속 설계에서는 coordinator, specialist agents, policy/reducer의 책임을 구체화한다.

## 참고 문서

- Graph-based workflows: https://adk.dev/graphs/
- Dynamic workflows: https://adk.dev/graphs/dynamic/
- Collaborative workflows: https://adk.dev/workflows/collaboration/
