# [ADR-004] 비선형적 실험 워크플로우를 위한 가드레일 및 상태 반응형 그래프 아키텍처 선정

- **상태(Status):** 제안됨(Proposed)
- **날짜(Date):** 2026년 6월 11일
- **컨텍스트:** Google ADK(Agent Development Kit) Python 2.x, Gemini Flash 계열, 모놀리식 아키텍처 기반 연구/실험 자동화 시스템

## 1. 요구사항 및 제약사항(Requirements & Constraints)

### 비즈니스 및 UX 요구사항(PRD + 팀 진화 방향)

- **R1. 4단계 Phase 명시:** 시스템은 데이터 분석 -> 가설 도출 -> 세부 실험 계획 -> 실험 평가로 이어지는 도메인 프로세스를 구조적으로 지원해야 한다.
- **R2. 단계 내 자유 토론 및 HITL:** 사용자는 각 단계 내에서 에이전트와 제한 없이 자유롭게 대화하고 산출물을 수정, 보정, 승인할 수 있어야 한다.
- **R3. 비선형적 역주행 및 Backtracking:** 사용자는 순차적 흐름을 따르지 않고 임의의 시점, 예를 들어 4단계 평가 중 1단계 데이터 분석으로 돌아가 조건을 변경하고 파이프라인을 재가동할 수 있어야 한다.
- **R4. 자유 대화 기반 상태 반응성:** 상태 변경은 UI가 명시적으로 넘기는 `target_phase`나 버튼 이벤트에 의존하지 않는다. 사용자의 자유 대화 속 표현에서 상태 변경 후보를 감지하고, agent core 내부에서 이를 구조화해야 한다.

### 기술적 제약사항(Technical Constraints)

- **C1. 프레임워크 제약:** Google ADK Python 2.x와 Gemini Flash 계열 모델의 네이티브 기능을 기반으로 모놀리식 내부 코어를 구현한다. 단, 현재 구현에서는 ADK GraphWorkflow API를 섣불리 가정하지 않고 코드 레벨의 macro graph와 state reducer를 먼저 둔다.
- **C2. 비결정성 통제:** 자유 대화로 인해 발생할 수 있는 AI의 무작위 행동, 환각, 엉뚱한 도구 호출, 흐름 이탈로 인한 시스템 실패율을 최소화해야 한다.
- **C3. 콘텍스트 최적화:** 역주행 시 사용자의 과거 실패 경험은 자산으로 유지하되, 무거운 원시 데이터나 중복 대화가 누적되어 프롬프트가 비대화되는 현상은 차단해야 한다.
- **C4. 기존 계약 보존:** Java -> Python 계약은 conversation-first 형태를 유지한다. UI/Java가 workflow state를 authoritative하게 보내는 구조로 바꾸지 않는다.
- **C5. Elastic 단일 저장소 원칙 확장:** scale-out을 위해 Agent Core runtime repository도 ElasticSearch를 사용한다. 단, 승인된 business document와 runtime coordination document는 계약상 분리한다.

## 2. 기술적 대안 후보(Technical Alternatives)

제시된 세 가지 대안은 모두 Google ADK 2.x 환경에서 구동 가능하며, 사용자의 비선형적 역주행과 자유 토론을 수용할 수 있는 후보들이다. 다만 본 결정은 PRD에만 종속된 해석이 아니라, Gemini 논의와 팀의 최신 방향성인 "대화형 상태 반응 agent core"를 상위 기준으로 삼는다.

### Alternative A: ADK 2.x 계층형 라우터 패턴(Central Router with Hierarchical Task API)

- **구조:** 최상위 중앙 마스터 라우터 에이전트를 두고, 4개 단계를 각각 전담하는 하위 워커 에이전트들을 트리 형태로 배치한다.
- **동작:** 사용자가 역주행을 요구하면 마스터 라우터 LLM이 대화 인텐트를 해석하여 해당 단계의 하위 워커에게 제어권을 동적으로 이양한다. 과거 대화 기록은 라우터의 상위 세션 메모리에 누적 관리된다.
- **한계:** 라우터 LLM이 상태 전이의 실질적 권한자가 되기 쉽다. 복잡한 자유 대화에서 phase 오분류가 발생하면 엉뚱한 worker가 실행될 수 있고, 전체 대화 누적으로 인해 prompt bloat가 커진다.

### Alternative B: ADK 2.x 상태 반응형 블랙보드 패턴(State-Reactive Blackboard)

- **구조:** 에이전트 간 명시적인 호출 관계를 제거하고, 모놀리식 내부의 공유 데이터 공간과 상태 변경 이벤트에 의존한다.
- **동작:** 사용자가 "데이터 분석 조건을 바꾸자"고 하면 공유 상태 객체의 값이 변경된다. 4개의 독립 에이전트는 상태 변화 이벤트를 모니터링하다가 자신의 조건이 충족되면 자율적으로 개입한다.
- **한계:** 유연성은 높지만, 상태 변화에 따른 체인 반응을 코드 레벨에서 추적하기 어렵다. 특히 빠른 연속 입력과 비동기 worker 실행이 겹치면 race condition과 디버깅 난도가 커진다.

### Alternative C: ADK 2.x 상태 반응형 그래프 워크플로우 패턴(Macro-Graph + Micro-State Hybrid) -- 채택안

- **구조:** 4대 단계의 거시적 진입 자격과 전이 경로는 코드 레벨 Macro-Graph로 통제한다. 단계 내부에서는 공유 상태 벡터의 `user_intent`, `current_phase`, `target_phase`에 따라 worker skill을 동적으로 선택한다.
- **동작:** 역주행 제어는 LLM이 그래프를 직접 꺾는 방식이 아니다. 자유 대화에서 추출된 `StateDelta` 후보를 deterministic reducer가 검증하고, 검증된 `SharedStateVector` 변화에 따라 목적 phase로 점프한다.
- **핵심 원칙:** LLM은 상태 변경의 권한자가 아니라 parser/proposer다. 실제 전이는 코드 레벨 reducer가 수행한다.
- **콘텍스트 전략:** 역주행 시 과거 heavy artifact는 프롬프트에 직접 주입하지 않는다. 대신 phase artifact store에 격리하고, 과거 실패 경험과 변경 이유만 compact lesson 형태로 델타 오버레이한다.

## 3. 기술별 트레이드오프 분석(Trade-off Analysis)

| 평가 항목 | Alternative A: 계층형 라우터 | Alternative B: 반응형 블랙보드 | Alternative C: 상태 반응형 그래프 |
|---|---|---|---|
| **C2: 비결정성 통제** | **중간(Marginal)**. 최상위 라우터 LLM이 복잡한 역주행 의도를 잘못 판단하면 엉뚱한 하위 worker를 깨울 위험이 남는다. | **낮음(Poor)**. 상태 변화에 따른 에이전트들의 자율 개입으로 제어 흐름의 추적성과 예측 가능성이 가장 떨어진다. | **우수(Excellent)**. 자유문 해석은 `StateDelta` 후보에 머물고, 실제 phase 전이는 reducer가 수행하므로 큰 흐름의 일탈을 줄일 수 있다. |
| **C3: 콘텍스트 무결성** | **낮음(Critical)**. 마스터 라우터가 전체 대화와 하위 산출물을 계속 소유하면 prompt bloat가 심각해진다. | **중간(Marginal)**. 블랙보드에 모든 artifact가 남아 있어 worker가 비대한 상태 객체를 파싱할 위험이 있다. | **우수(Excellent)**. heavy artifact와 prompt context를 분리하고 compact lesson만 델타로 주입하여 컨텍스트를 얇게 유지한다. |
| **R4: 자유 대화 기반 상태 반응성** | **중간(Good)**. 라우터가 자연어 상태 변화를 감지할 수 있으나, 라우터 판단 자체가 실행 권한으로 이어지기 쉽다. | **우수(Good)**. 상태 변화에 민감하게 반응하지만, 상태 변화의 권위와 충돌 해결 규칙이 불명확해질 수 있다. | **최상(Excellent)**. 자유 대화에서 상태 변화 후보를 추출하되, reducer가 authoritative transition을 담당하므로 UX와 안정성을 모두 확보한다. |
| **구현 및 아키텍처 복잡도 제어** | **우수(Good)**. 빠르게 구현 가능하나 장기적으로 라우터 프롬프트가 복잡해진다. | **중간(Marginal)**. 이벤트 기반 비동기 디버깅과 관측성 설계가 어려워진다. | **중간(Marginal)**. 초기 StateVector/reducer/lock 설계 공수는 크지만, edge explosion을 막아 최종 복잡도를 제어한다. |

## 4. 우선순위 가치 위계 및 최종 결정(Value Hierarchy & Decision)

### 우리의 아키텍처 가치 위계

1. **C3: 콘텍스트 무결성**  
   Gemini Flash 계열 모델의 추론 및 도구 호출 정확도를 유지하기 위해 prompt bloat를 막는다.
2. **C2: 비결정성 통제**  
   엔터프라이즈 프로덕션 레벨의 실행 흐름을 보장하기 위해 LLM이 workflow 권한자가 되지 않게 한다.
3. **R4/R3: 유저 인터랙션의 비선형적 자유도**  
   사용자는 UI 명령이 아니라 자유 대화로 phase 이동과 조건 변경을 요청할 수 있어야 한다.
4. **초기 개발 공수 감수**  
   StateVector, reducer, artifact isolation, thread lock 구축 비용을 감수한다.

### 최종 결정 사유

- **Alternative A 기각:** 구현이 직관적이고 빠르지만, 대화가 길어질수록 거대한 산출물과 잡담이 라우터 컨텍스트에 누적된다. 또한 라우터 LLM이 phase 전이의 실질적 권한자가 되기 쉬워 C2를 충분히 만족하지 못한다.
- **Alternative B 기각:** 비선형성을 다루기에 유연하지만, 상태 변화에 따른 동시다발적 체인 반응을 코드 레벨에서 통제하기 어렵다. 모놀리식 내부 비동기 loop에서 race condition과 관측성 부채가 커진다.
- **Alternative C 채택:** 거시적 단계 제어와 미시적 상태 반응을 분리한다. 자유 대화에서 `StateDelta` 후보를 추출하되, 실제 상태 전이는 deterministic reducer가 담당한다. 이 방식은 PRD의 4단계 요구를 보존하면서도 팀의 최신 방향성인 대화형, 비선형, 상태 반응 agent core로 진화할 수 있다.

## 5. 채택 아키텍처의 구체 설계(Concrete Design)

### 5.1 Conversation-Derived StateDelta

상태 변경은 UI가 넘기지 않는다. agent core는 사용자 자유문에서 다음 구조의 후보를 추출한다.

```json
{
  "intent": "backtrack",
  "target_phase": "DATA_ANALYSIS",
  "restart_from_phase": "DATA_ANALYSIS",
  "mutation": {
    "metric": "save_rate",
    "threshold_lift": 2.0
  },
  "confidence": 0.82,
  "requires_confirmation": false
}
```

이 후보는 바로 실행되지 않는다. deterministic reducer가 현재 상태, phase, confidence, mutation을 검토한 뒤 실제 `SharedStateVector`를 변경한다.

### 5.2 SharedStateVector

공유 상태 객체는 phase와 intent를 소유하되, 외부 계약의 일부가 아니다. Java/Python 경계는 conversation-first 계약을 유지한다.

- `current_phase`: 현재 agent core가 머무는 phase
- `target_phase`: 다음 실행 또는 역주행 목적 phase
- `user_intent`: `INITIAL_RUN`, `FREE_CHAT`, `BACKTRACK`, `APPROVE`
- `compact_lessons`: 과거 실패/기각/변경 사유의 짧은 요약
- `phase_artifacts`: heavy artifact 격리 저장소
- `active_chat_history`: 현재 phase의 제한된 대화 버퍼
- `revision`: 상태 전이 버전
- `active_run_id`: 향후 obsolete run cancellation을 위한 실행 id

### 5.3 Macro-Graph Layer

현 단계에서는 ADK GraphWorkflow API를 직접 도입하지 않는다. 대신 코드 레벨 phase dispatcher로 Macro-Graph를 구현한다.

- `DATA_ANALYSIS -> HYPOTHESIS_GEN -> EXPERIMENT_PLAN -> EXPERIMENT_EVAL` 순차 흐름을 기본값으로 둔다.
- `BACKTRACK` 감지 시 `target_phase`부터 downstream worker를 재실행한다.
- reviewer backtracking과 user backtracking을 분리한다. reviewer backtracking은 품질 검증 실패에 따른 내부 재시도이고, user backtracking은 자유 대화에서 파생된 상태 전이다.

### 5.4 Micro-State Layer

각 phase 내부에서는 `user_intent`에 따라 skill 또는 worker prompt pack이 달라진다.

| Phase | Intent | 실행 전략 | Prompt boundary |
|---|---|---|---|
| DATA_ANALYSIS | INITIAL_RUN | analyst worker 실행 | 사용자 질의 + 분석 window + evidence tool |
| DATA_ANALYSIS | BACKTRACK | analyst worker 재실행 | 신규 변경 요구 + compact lessons + scoped evidence |
| HYPOTHESIS_GEN | FREE_CHAT | chat/debate 응답 | 현재 hypothesis artifact + active chat history |
| EXPERIMENT_PLAN | INITIAL_RUN/BACKTRACK | writer worker 실행 | 검증된 hypothesis snapshot |

현재 구현은 skill file hot-swapping을 직접 도입하지 않고, 이 경계를 worker facade와 prompt pack으로 먼저 표현한다. 향후 ADK skill runtime이 안정화되면 같은 StateVector를 기반으로 실제 skill hot-swapping으로 교체한다.

### 5.5 Context Pruning and Delta Overlay

heavy artifact는 prompt에 직접 누적하지 않는다. artifact는 phase별 저장소에 격리하고, prompt에는 필요한 snapshot 또는 compact lesson만 넣는다.

이 원칙은 의도적인 부채를 만든다. 과거 원문 디테일을 즉시 기억하지 못할 수 있지만, 그 대가로 현재 phase의 추론 정확도와 도구 호출 안정성을 얻는다.

### 5.6 Elastic Runtime Repository

`SharedStateVector`와 `StateDelta`는 Python process memory에만 의존하지 않는다. scale-out과 재시작 복구를 위해 ElasticSearch를 Agent Core runtime repository로 사용한다.

단, 이 저장은 승인된 business persistence가 아니다.

- `growth_briefs`, `calendar_events`: Java가 승인 후 쓰는 business document
- `agent_thread_states`, `agent_state_deltas`, `agent_runtime_artifacts`: Python Agent Core가 쓰는 runtime-only coordination document
- `workspace_id`: tenant/data boundary, `campaign_id`: no-login MVP의 working context. Agent Core의 Elastic 조회는 가능한 모든 경로에서 둘을 함께 사용한다.

따라서 기존 "승인 전 후보 비저장" 원칙은 다음처럼 정교화한다.

> 승인 전 후보는 business document로 영속 저장하지 않는다. 단, scale-out과 장애 복구를 위해 Agent Core는 Elastic의 runtime-only index에 TTL이 있는 state/artifact snapshot 또는 ref를 저장할 수 있다.

Runtime Elastic 계약 초안은 `contracts/07-agent-runtime-elastic`에 둔다.

## 6. 잔재하는 구조적 리스크(Residual Risks)

### Risk 1: 인지적 맹점(Cognitive Blind Spot)으로 인한 고맥락 대화 실패

- **리스크의 본질:** 콘텍스트 노이즈를 제거하기 위해 과거 단계의 무거운 원시 데이터와 세부 대화 디테일을 프롬프트에서 제외한다. 에이전트는 과거 맥락 일부에 대해 구조적 망각 상태에 놓인다.
- **영향:** 사용자가 "아까 1단계 분석할 때 내가 넣었던 소스 코드의 45번째 라인 기억하지?"처럼 상세 원문을 기습적으로 인용하면 agent가 복구하지 못할 수 있다.
- **완화책:** memory manager는 raw artifact 재조회가 가능한 경우 artifact store에서 복구한다. 복구 불가능하면 사용자가 해당 원문을 다시 공유하도록 graceful fallback 문구를 제공한다.

### Risk 2: Macro-State 동기화 지연 및 상태 정합성 레이스 컨디션

- **리스크의 본질:** 그래프 전이 조건을 공유 상태 벡터에 모으기 때문에, 빠른 연속 입력이 들어올 때 상태 전이와 worker 실행이 겹칠 수 있다.
- **영향:** 사용자의 최신 의도와 active worker runtime이 일시적으로 어긋날 수 있다.
- **완화책:** thread별 `asyncio.Lock`으로 상태 전이와 phase 실행을 직렬화한다. `revision`과 `active_run_id`를 통해 향후 obsolete run cancellation을 추가한다.

### Risk 3: StateDelta 오분류

- **리스크의 본질:** 자유 대화에서 추출된 `StateDelta` 후보가 잘못될 수 있다.
- **영향:** 분석 재실행이 불필요하게 발생하거나, chat으로 처리해야 할 요청이 backtrack으로 처리될 수 있다.
- **완화책:** LLM 또는 heuristic interpreter는 후보만 제안한다. reducer는 confidence, 현재 phase, target phase, mutation을 검증한다. 모호한 경우 `requires_confirmation=true`로 사용자 확인을 요청한다.

### Risk 4: Runtime Document와 Business Document의 의미 혼동

- **리스크의 본질:** Elastic을 runtime repository로 확장하면 승인 전 draft가 Elastic에 존재할 수 있다. 이를 승인된 business record로 오해하면 HITL 불변성이 깨진다.
- **영향:** 미승인 후보가 continuity, evidence, calendar, growth brief 검색에 섞일 수 있다.
- **완화책:** runtime index를 `agent_*` prefix로 분리하고 TTL, `runtime_only=true`, reader 제한을 둔다. business query와 evidence wrapper는 runtime index를 읽지 않는다.

## 7. 현재 구현 상태(Current Implementation)

이 ADR의 첫 단계 구현은 다음 파일에 반영한다.

- `apps/agent/app/runtime/state.py`: `SharedStateVector`, `StateDelta`, `reduce_state`
- `apps/agent/app/runtime/thread_store.py`: thread별 state와 turn lock
- `apps/agent/app/agents/workers.py`: 자유문 기반 turn interpreter
- `apps/agent/app/orchestrator.py`: `StateDelta -> reducer -> phase dispatcher` 흐름
- `apps/agent/tests/test_state_reactive_orchestrator.py`: 자유문 역주행 및 phase-local chat 검증
- `docs/architecture/agent-core-v2-design.md`: repository, delegation policy, artifact, concurrency, observability 초안
- `contracts/07-agent-runtime-elastic`: Elastic runtime repository 계약 초안

향후 작업은 ADK GraphWorkflow 직접 도입, skill hot-swapping 고도화, memory manager의 raw artifact 재조회, obsolete run cancellation 순서로 진행한다.
