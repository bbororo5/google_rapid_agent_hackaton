# runtime — State / Memory 컴포넌트

"지금 이 대화가 어느 단계이고 무엇을 만들어 냈는지"를 들고 있고, 그것을
저장·복원한다. LLM 호출은 여기 없다 — 순수하게 상태와 저장이 일이다.

인프라 레이어의 **State / Memory** 컴포넌트다.

## 공개 진입점

| API | 역할 |
|---|---|
| `ConversationState` | 한 대화 스레드의 현재 상태 |
| `ProposedChange` | 자연어에서 추출된 상태 변경 제안 |
| `apply_proposed_change` | 변경 제안을 실제 상태 변화로 확정하는 reducer |
| `AgentRuntimeRepository` | 상태, 메시지, artifact, episode 저장소 계약 |
| `get_runtime_repository` | 설정에 따른 runtime repository 선택 |
| `StateCache`, `get_state_cache` | Redis/InMemory state cache |
| `Episode`, `recent_episode_context`, `restore_from_episode` | 장기 기억 조회와 복원 |

## 저장 구조 (2단)

```
빠른 캐시 (Redis)        ◀── 매 턴 먼저 읽음 (state_cache.py)
   │  없으면
   ▼
권위 저장소 (Elastic)    ◀── 진짜 원본 (repository.py)
   └ 상태 / 변경로그 / 결과물 / 메시지 / 에피소드
```

캐시는 언제 날아가도 권위 저장소에서 다시 채울 수 있다(권위는 항상 Elastic).

## 상태가 바뀌는 규칙 (가장 중요)

```
LLM이 변경안 제안 (ProposedChange)
        │
        ▼
판정 (apply_proposed_change + transitions.py)  ── 코드가 결정. LLM은 결정 못 함.
        │  수락 / 되묻기 / 거절
        ▼
ConversationState 갱신 (state.py)
```

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [state.py](state.py) | 대화 상태(ConversationState) + 변경안/판정 정의 + `apply_proposed_change`(리듀서) |
| [transitions.py](transitions.py) | 제안을 실제 상태 변화로 확정하는 규칙 그래프 (리듀서의 판정부) |
| [repository.py](repository.py) | 권위 저장소 (메모리/Elastic 두 구현). 상태·결과물·에피소드 읽고 씀 |
| [state_cache.py](state_cache.py) | 빠른 상태 캐시 (Redis/InMemory). 매 턴 Elastic 왕복을 줄임 |
| [thread_store.py](thread_store.py) | 프로세스 안의 살아있는 스레드 핸들 + 화면 블록 타임라인 |
| [blocks.py](blocks.py) | 화면에 보낼 블록(텍스트/활동/아티팩트/승인…) 만들기 |
| [episode.py](episode.py) | 에피소드 = 한 라운드 기록 + 상태 스냅샷 (되돌리기 단위) |
| [episode_query.py](episode_query.py) | 과거 에피소드를 LLM 컨텍스트용으로 간추리기 |
| [restore.py](restore.py) | 과거 에피소드 시점으로 상태 되돌리기 |

> 용어가 어렵다면 [../GLOSSARY.md](../GLOSSARY.md) 참고. 옛 이름(delta/reducer/hot)
> ↔ 새 이름(ProposedChange/apply_proposed_change/state_cache) 대조표가 있다.
