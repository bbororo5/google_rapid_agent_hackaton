# 도메인 단어 사전 (읽기 위한 맥락)

코드의 핵심 명사를 일상어로 옮긴 표. 파일을 읽다 막히면 여기서 단어를 번역한다.

## 이름 규칙 (가장 중요)

메서드 이름은 **주어 + 동사 + 목적어** 문장으로 읽히게 짓는다. 주어는 그 메서드가
달린 객체(self)다. 호출하면 "(이 객체가) ~을 ~한다"로 읽혀야 한다.

| 좋은 이름 | 읽으면 |
|---|---|
| `runner.load_analysis_signals(turn)` | 러너가 분석 신호를 불러온다 (동사+목적어) |
| `runner.stop_if_cancelled(turn)` | 러너가 취소됐으면 멈춘다 |
| `runner.enter_phase(turn)` | 러너가 단계로 진입한다 |

나쁜 예: `check_cancelled` — 무엇을 어떻게 하는지 안 보임(점검만 하고 끝?).
→ `stop_if_cancelled` 로 "멈춘다"는 동작과 조건을 드러낸다.

또한 함수 첫 줄에 `# 목표: ...` 주석으로 그 함수가 이루려는 바를 먼저 선언한다.

## 대화 / 상태

| 코드 단어 | 일상어 뜻 |
|---|---|
| `ConversationState` (구 `SharedStateVector`) | 한 대화 스레드의 현재 상태 전부 |
| `current_phase` | 지금 어느 단계인가 (분석/가설/계획/평가) |
| `phase_artifacts` | 단계별로 만들어 낸 결과물 (신호/가설/계획) |
| `phase_artifact_refs` | 저장소에 넣어 둔 결과물의 영수증(ID) 목록 |
| `scope` | 이 대화가 속한 작업공간/캠페인/스레드 묶음 |

## 한 턴(turn)의 흐름

| 코드 단어 (현재) | 일상어 뜻 | 구 이름 |
|---|---|---|
| turn | 사용자 메시지 한 번 + 그 처리 한 묶음 | |
| interpret | 자유 문장을 "무슨 뜻"으로 해석 | |
| `ProposedChange` | LLM이 제안한 "이렇게 바꾸자" 변경안 (아직 확정 아님) | `StateDeltaProposal` |
| `apply_proposed_change` | 변경안을 받아 실제 상태로 확정하는 함수(리듀서) | `reduce_state` |
| `ChangeDecision` | 그 판정 결과 묶음 (수락/되묻기/거절) | `ReducerDecision` |
| `ChangeLogEntry` | 저장소에 남기는 변경 이력 한 건 | `DeltaEvent` |
| `TurnIntent` | 한 턴의 의도 (CHAT, START_ANALYSIS ...) — 변경안에 붙음 | `DeltaIntent` |
| `UserIntent` | 상태에 누적 기록되는 사용자 의도 (INITIAL_RUN, BACKTRACK ...) | `IntentType` |
| delegation | 이 턴을 누가 처리할지 (직접답변/단계실행/되묻기) | |
| route | 판정에 따라 실제 처리기로 보내기 | |

> `TurnIntent` 와 `UserIntent` 는 이제 이름으로 구분된다. 한 턴의 즉각 의도 vs
> 상태에 쌓이는 누적 의도. 의미가 다르므로 합치지 않는다.

## 단계 실행 (라운드)

| 코드 단어 | 일상어 뜻 |
|---|---|
| round / RoundRunner | 한 단계(분석 등)를 한 번 실행하는 일 |
| analyst / strategist / writer | 분석가 / 전략가 / 작성자 (각 단계의 LLM 일꾼) |
| signal | 신호 = 지표에서 발견한 두드러진 변화 |
| hypothesis | 가설 = 신호의 원인 추정 |
| experiment_plan | 실험 계획 = 다음에 해 볼 실험들 |
| reviewer / guardrail | 계획이 승인 가능한지 검사하는 관문 |

## 저장 / 스트리밍

| 코드 단어 (현재) | 일상어 뜻 | 구 이름 |
|---|---|---|
| `RuntimeArtifact` | 저장소에 보관하는 단계 결과물 한 건 | |
| repository | 영속 저장소 (메모리 또는 Elastic) | |
| `StateCache` / `state_cache` (state_cache.py) | 빠른 임시 캐시 (Redis) | `HotStateStore`/`hot_store` |
| emitter / block | 사용자 화면에 보낼 메시지 조각을 흘려보내는 도구 | |
| episode | 과거 한 라운드의 기록 (되돌리기/기억에 사용) | |
