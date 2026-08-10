# Python Agent Core v2 설계 초안

상태: Draft  
날짜: 2026-06-11  
관련 ADR: `docs/architecture/adr/05-state-reactive-workflow.md`

## 0. 전제

PRD의 핵심 제품 루프는 `Signal -> Hypothesis -> Experiment -> Approval -> Brief -> Continuity`다. 사용자는 UI 단계 버튼을 따라가는 것이 아니라 자유 대화 main stream에서 질문, 수정, 승인, 연속 분석을 수행한다. 따라서 Python Agent Core v2의 핵심은 다음이다.

- 자유 대화에서 `StateDelta`를 structured output으로 추출한다.
- `StateDelta`는 상태 전이 제안서이며, authoritative state가 아니다.
- deterministic reducer가 `SharedStateVector`를 갱신한다.
- 오케스트레이터는 control plane이다.
- phase sub-agent는 의미 있는 도메인 추론과 artifact 변경이 필요한 경우에만 호출한다.
- repository 구현체는 ElasticSearch다. 단, business document와 runtime coordination document는 계약상 분리한다.

## 1. Repository / Elastic Contract 검토

### 1.1 현재 계약 상태

현재 `contracts/03-java-elastic`은 Java <-> Elastic business document 계약이다. 주요 index는 다음 세 축이다.

- `content_posts`: CSV import 결과
- `growth_briefs`: 승인된 결과
- `calendar_events`: 승인된 실험의 calendar projection

또한 기존 PRD/ADR은 다음 불변식을 가진다.

- Python Agent Core는 승인 전 후보를 business document로 저장하지 않는다.
- 승인된 산출물만 `growth_briefs`, `calendar_events`에 들어간다.
- Java가 final approval persistence를 소유한다.

따라서 `SharedStateVector`, `StateDelta`, phase-local draft artifact를 Elastic에 저장하려면 기존 `contracts/03-java-elastic`에 단순 추가하면 의미가 섞인다. 이는 business persistence가 아니라 agent runtime coordination이다.

### 1.2 판단

계약 수정은 필요하다. 다만 `contracts/03-java-elastic`을 확장하기보다, 별도 내부 계약을 둔다.

권장 신규 계약:

```text
contracts/07-agent-runtime-elastic/
```

경계:

```text
Python Agent Core <-> ElasticSearch Runtime Repository
```

이 계약은 customer-facing business record가 아니라 다음을 정의한다.

- agent thread runtime state
- state delta event
- optional runtime artifact snapshot/ref
- lock/revision/idempotency 규칙
- TTL/retention 규칙

### 1.3 중요한 문구 수정 방향

기존 "승인 전 후보는 어떤 저장소에도 들어가지 않는다"는 문장은 v2에서 다음처럼 정교화해야 한다.

> 승인 전 후보는 business document로 영속 저장하지 않는다. 단, scale-out과 장애 복구를 위해 Agent Core는 Elastic의 runtime-only index에 TTL이 있는 draft snapshot 또는 artifact ref를 저장할 수 있다. 이 runtime document는 승인된 `growth_briefs`나 `calendar_events`가 아니며, continuity/evidence/business query의 대상이 아니다.

이렇게 해야 Elastic repository와 HITL 승인 불변성이 동시에 산다.

### 1.4 ScopeContext와 대화 메모리

로그인/권한 기능이 없는 MVP에서도 `workspace_id`와 `campaign_id`의 의미를 섞지 않는다.

- `workspace_id`: tenant/data boundary. 현재는 `demo_workspace` 같은 기본값을 쓸 수 있지만, 모든 business/runtime query에 포함한다.
- `campaign_id`: 사용자가 체감하는 primary working context. Agent Core가 캠페인 맥락, thread state, conversation memory를 묶어 읽는 기준이다.
- `thread_id`: 같은 campaign 안에서 이어지는 대화 세션 식별자다.

Python Agent Core는 매 턴 다음 순서로 scope를 확정한다.

1. Java payload의 `workspace_id`, `campaign_id`, `thread_id`를 우선 사용한다.
2. payload 값이 비어 있으면 `agent_thread_states`의 persisted `ScopeContext`로 복원한다.
3. `workspace_id`만 없고 `campaign_id`가 있으면 no-login MVP 기본값인 `demo_workspace`를 사용한다.
4. `campaign_id`를 복원하지 못하면 분석/역주행 같은 agent work를 시작하지 않고 recoverable error block을 반환한다.

Turn setup은 full history를 prompt에 넣지 않는다. Elastic에서 다음을 bounded load한 뒤 compact state summary로 축약한다.

- `campaigns`: campaign context. Java business contract 소유.
- `agent_thread_states`: 최신 `SharedStateVector`. Python runtime contract 소유.
- `agent_thread_messages`: Java가 저장한 user/assistant/system timeline. Python은 read-only memory source로 사용한다.
- `agent_runtime_artifacts`: 승인 전 runtime-only artifact snapshot/ref. Python runtime contract 소유.

`agent_thread_messages`의 기본 writer는 Java다. Java는 frontend user message를 먼저 받고, Python stream을 수신한 뒤 assistant/system summary를 저장한다. Python이 같은 index에 assistant message를 직접 쓰면 중복 owner 문제가 생기므로 기본 설계에서는 읽기 전용으로 둔다.

## 2. Turn Interpreter / StateDelta 스키마 초안

Turn Interpreter는 Gemini structured output을 사용한다. 출력은 `StateDeltaProposal`이며, reducer가 검증하기 전에는 상태가 아니다.

```python
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class PhaseType(str, Enum):
    DATA_ANALYSIS = "DATA_ANALYSIS"
    HYPOTHESIS_GEN = "HYPOTHESIS_GEN"
    EXPERIMENT_PLAN = "EXPERIMENT_PLAN"
    EXPERIMENT_EVAL = "EXPERIMENT_EVAL"


class DeltaIntent(str, Enum):
    SMALLTALK = "smalltalk"
    STATUS_QUESTION = "status_question"
    EXPLAIN_LAST_RESULT = "explain_last_result"
    PHASE_DISCUSSION = "phase_discussion"
    ARTIFACT_REVISION = "artifact_revision"
    BACKTRACK = "backtrack"
    APPROVE = "approve"
    REJECT = "reject"
    RUN_PIPELINE = "run_pipeline"
    CLARIFY = "clarify"


class ResponseMode(str, Enum):
    DIRECT = "direct"
    DELEGATE = "delegate"
    RERUN = "rerun"
    CLARIFY = "clarify"


class StateDeltaProposal(BaseModel):
    intent: DeltaIntent
    response_mode: ResponseMode
    target_phase: PhaseType | None = None
    restart_from_phase: PhaseType | None = None
    mutation: dict[str, Any] = Field(default_factory=dict)
    referenced_artifact_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool = False
    clarification_question: str | None = None
    rationale: str | None = Field(
        default=None,
        description="Tracing/debug only. Never used as workflow authority.",
    )
```

`SharedStateVector`의 핵심 필드는 다음과 같다.

```python
class ScopeContext(BaseModel):
    workspace_id: str
    campaign_id: str
    thread_id: str


class SharedStateVector(BaseModel):
    scope: ScopeContext
    current_phase: PhaseType
    target_phase: PhaseType
    user_intent: str
    revision: int
    active_run_id: str | None
    active_artifact_id: str | None
    pending_approval_id: str | None
    compact_lessons: list[dict]
    phase_artifact_refs: dict[str, list[str]]
    active_chat_history: list[dict]
```

Reducer는 다음 필드를 authoritative state로 직접 믿지 않는다.

- `intent`
- `response_mode`
- `target_phase`
- `mutation`

모든 필드는 현재 `SharedStateVector`, confidence threshold, phase order, pending approval, active artifact 존재 여부로 검증한다.

## 3. Delegation Policy 초안

오케스트레이터는 매 턴을 다음 셋 중 하나로 보낸다.

1. direct reply
2. phase-agent delegation
3. pipeline rerun

### 3.1 Direct Reply

오케스트레이터가 직접 처리한다.

조건:

- 상태 조회
- 진행 제어
- 단순 설명
- 인사/ack
- 명확한 승인/거절 신호
- 모호해서 확인 질문이 필요한 경우
- artifact 변경 없음
- tool 호출 없음
- phase 전문 추론 없음

예:

```text
"지금 어디까지 됐어?"
"이 카드가 뭐야?"
"고마워"
"계속해"
```

정책:

```python
def should_reply_directly(delta, state):
    return (
        delta.response_mode == ResponseMode.DIRECT
        and not delta.mutation
        and not delta.referenced_artifact_ids
        and delta.intent in {
            DeltaIntent.SMALLTALK,
            DeltaIntent.STATUS_QUESTION,
            DeltaIntent.EXPLAIN_LAST_RESULT,
            DeltaIntent.CLARIFY,
            DeltaIntent.APPROVE,
            DeltaIntent.REJECT,
        }
    )
```

### 3.2 Phase-Agent Delegation

현재 phase 내부에서 의미 있는 대화나 artifact 수정이 필요할 때 호출한다.

조건:

- 현재 phase artifact의 의미 있는 수정
- 가설/실험안 토론
- 도메인 판단 필요
- artifact 변경 필요
- evidence/tool 재조회 필요
- phase-local reasoning 필요

예:

```text
"이 가설이 왜 더 그럴듯한지 설명해줘."
"이 실험을 YouTube용으로 바꿔줘."
"BTS hook 중심으로 제목을 더 짧게 수정해줘."
```

정책:

```python
def should_delegate_to_phase_agent(delta, state):
    return (
        delta.response_mode == ResponseMode.DELEGATE
        or delta.intent in {
            DeltaIntent.PHASE_DISCUSSION,
            DeltaIntent.ARTIFACT_REVISION,
        }
    ) and delta.intent != DeltaIntent.BACKTRACK
```

### 3.3 Pipeline Rerun

상류 artifact를 invalidation해야 할 때 실행한다.

조건:

- target phase가 current phase보다 앞 단계
- mutation이 upstream artifact에 영향을 줌
- 사용자가 "처음부터", "다시 분석", "기준 바꿔"라고 명시

예:

```text
"저장률 말고 공유 수 기준으로 처음 분석부터 다시 보자."
"TikTok 빼고 YouTube/Instagram만 보고 다시 가설 세워줘."
```

정책:

```python
def should_rerun_pipeline(delta, state):
    return (
        delta.response_mode == ResponseMode.RERUN
        or delta.intent == DeltaIntent.BACKTRACK
        or (
            delta.target_phase is not None
            and phase_order(delta.target_phase) < phase_order(state.current_phase)
        )
    )
```

## 4. Phase Agent Contract

이번 작업 범위에서는 실제 phase agent 상세 구현을 보류한다. v2 기반 인프라에서는 다음 경계만 고정한다.

- phase agent는 state를 직접 commit하지 않는다.
- phase agent는 artifact patch 또는 structured draft만 반환한다.
- phase 이동/역주행은 오케스트레이터 reducer만 수행한다.
- phase agent가 대화 중 backtrack 신호를 감지하면 `StateDeltaProposal` 또는 `EscalationRequest`를 반환한다.

상세 schema와 skill runtime은 다음 수정 계획에서 다룬다.

## 5. Artifact 저장 전략 초안

Elastic을 repository로 쓰되, 모든 artifact를 같은 방식으로 저장하지 않는다.

### 5.1 Index 구분

권장 index:

| Index | 목적 | 성격 |
|---|---|---|
| `agent_thread_states` | thread별 최신 `SharedStateVector` snapshot | mutable by optimistic revision |
| `agent_state_deltas` | `StateDelta` transition event log | append-only |
| `agent_runtime_artifacts` | 승인 전 runtime artifact snapshot 또는 ref | TTL, non-business |
| `agent_thread_messages` | Java-owned 대화 장기기억 | append-only, Python read-only |

### 5.2 저장 원칙

- `growth_briefs`와 `calendar_events`는 승인된 business document만 가진다.
- 승인 전 draft는 `agent_runtime_artifacts`에 TTL runtime document로만 저장한다.
- prompt에는 full artifact를 무조건 넣지 않는다.
- prompt에는 compact snapshot, artifact id, compact lesson만 넣는다.
- 큰 raw data는 `content_posts` 또는 object/ref로 유지하고 prompt에 직접 넣지 않는다.

### 5.3 Artifact Document 예시

```json
{
  "artifact_id": "art_thread_123_plan_v3",
  "thread_id": "thread_123",
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "phase": "EXPERIMENT_PLAN",
  "artifact_kind": "experiment_plan",
  "revision": 7,
  "payload": {
    "id": "plan_abc",
    "summary": "...",
    "items": []
  },
  "created_at": "2026-06-11T00:00:00Z",
  "expires_at": "2026-06-12T00:00:00Z",
  "runtime_only": true
}
```

## 6. 동시성 / 실행 모델 검토

PRD 기준으로 같은 사용자가 같은 세션에서 여러 요청을 동시에 보내는 강한 시나리오는 핵심 플로우가 아니다. 주 UX는 단일 composer에서 사용자가 agent output을 보고 다음 메시지를 보내는 방식이다.

다만 다음 이유로 최소 방어는 필요하다.

- 네트워크 재시도
- 더블 클릭/중복 send
- 사용자가 진행 중 "중단해", "이 기준으로 봐"를 입력
- Java/Python scale-out 환경에서 같은 thread가 다른 pod로 들어감

따라서 v2 초기 전략은 full queueing system이 아니라 **single-flight + idempotency + revision check**다.

### 6.1 권장 정책

- 같은 `thread_id`에는 한 번에 하나의 active run만 허용한다.
- 동일 `command_id`는 최대 1회만 처리한다.
- active run 중 새 turn이 오면 정책적으로 셋 중 하나를 택한다.
  - `AGENT_BUSY` 반환
  - 한 개까지 pending turn으로 저장
  - cancel/backtrack intent만 우선 처리

MVP 권장:

- 일반 free-form turn은 active run 종료 후 재전송 안내 또는 Java pending queue 1개.
- `cancel`/명확한 backtrack은 active run cancellation 설계가 들어간 뒤 우선 처리.
- Elastic repository는 `revision` 기반 optimistic concurrency를 반드시 사용한다.

### 6.2 Elastic Commit

Elastic은 Redis처럼 `SET NX PX` lock이 없다. 따라서 구현은 다음 중 하나를 써야 한다.

1. optimistic concurrency control
   - `_seq_no`, `_primary_term` 또는 `revision` field 기반
   - stale write는 reject 후 reload/reduce
2. lock document
   - `agent_thread_locks` index에 lock doc 생성
   - TTL/heartbeat 필요
   - 해커톤 범위에서는 과할 수 있음

권장 v2 초기:

- `agent_thread_states`에 `revision` 저장
- update by query 금지
- state update는 expected revision을 조건으로 scripted update 또는 OCC로 commit
- conflict 발생 시 turn을 재평가하거나 `AGENT_BUSY`로 내려간다

## 7. Observability 초안

OpenInference/Phoenix span에는 기존 LLM/tool/reviewer 정보 외에 agent core state transition 정보를 추가한다.

### 7.1 필수 span attributes

```text
agent.thread_id
agent.workspace_id
agent.campaign_id
agent.state.revision_before
agent.state.revision_after
agent.phase.current
agent.phase.target
agent.delta.intent
agent.delta.response_mode
agent.delta.confidence
agent.reducer.decision
agent.delegation.mode
agent.repository.backend = "elastic"
agent.repository.conflict = true|false
```

### 7.2 Span hierarchy

```text
AGENT launchpilot.thread
  CHAIN launchpilot.turn_interpreter
  CHAIN launchpilot.reducer
  CHAIN launchpilot.delegation_policy
  CHAIN launchpilot.phase_agent or launchpilot.orchestrator
  GUARDRAIL launchpilot.reviewer_gate
  EVALUATOR launchpilot.validation
```

### 7.3 Event log correlation

`agent_state_deltas`의 delta event id를 span metadata에 넣는다.

```text
agent.delta.event_id = "delta_thread_123_0007"
```

Phoenix에서 실패 turn을 볼 때 다음을 함께 추적할 수 있어야 한다.

- interpreter가 무엇을 제안했는지
- reducer가 왜 승인/거절/다운그레이드했는지
- direct/delegate/rerun 중 무엇을 골랐는지
- Elastic commit conflict가 있었는지

## 8. 요약 결정

- Elastic repository는 채택 가능하다.
- 단, `contracts/03-java-elastic` business document 계약에 섞지 않는다.
- 신규 `contracts/07-agent-runtime-elastic` 계약이 필요하다.
- pre-approval draft 저장 금지 원칙은 "business document 금지"로 정교화한다.
- 동시성은 PRD상 핵심 시나리오는 아니지만, scale-out과 retry 때문에 revision/OCC는 필요하다.
- phase agent 상세는 다음 계획으로 미루고, 지금은 orchestrator, repository, reducer, delegation policy 기반을 먼저 고정한다.
