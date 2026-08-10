# 런타임 메모리 구현 설계: Redis 핫 상태 + Elastic 에피소딕 영속

상태: Draft  
날짜: 2026-06-11  
근거 ADR: `docs/architecture/adr/06-memory-management.md` ([ADR-005])  
관련 계약: `contracts/07-agent-runtime-elastic`

ADR-005를 실제 코드로 옮기기 위한 구현 설계다. 현재 코드를 기준으로 무엇이 바뀌고 무엇이 추가되는지, 그리고 어떤 순서로 구현할지를 정의한다.

## 0. 현재 구현 vs 목표 (gap)

현재 코드는 사실상 ADR-005의 Alternative A다.

| 측면 | 현재 (실측) | 목표 (ADR-005 채택안) |
|---|---|---|
| live 상태 거처 | `thread_store.py` 인메모리 `ThreadRecord.state` (프로세스 휘발) | Redis 핫 티어 (`hot_store`) |
| ES 상태 적재 | `committer.py`가 **매 턴** `repository.commit_state` (per-turn) | 체크포인트 write-back (의미 단위) |
| 에피소드 | 없음 | `agent_episodes` 인덱스 + 적재/조회 |
| 조회 | `load_recent_messages`(시간순 N개)만 | 에피소드 하이브리드 top-k (MVP: 필터+recency+raw) |
| 회귀 복원 | 없음 (재실행만 부분 존재) | 에피소드=checkpoint로 상태 재구성 |
| authoritative | ES `agent_thread_states` (OCC 구현됨) | 동일 유지. Redis는 working copy |

OCC(`if_seq_no`/`if_primary_term`)와 scope(`workspace_id+campaign_id`) 강제는 `repository.py`에 이미 구현되어 있어 그대로 재사용한다.

## 1. 컴포넌트 맵 (파일별 변경/신규)

신규:
- `app/runtime/hot_store.py` — Redis 핫 상태 계층(`RedisHotStore` + 오프라인용 `InMemoryHotStore`).
- `app/runtime/episode.py` — `Episode` 모델 + `EpisodeBuilder`(직전 체크포인트 이후 버퍼 → 에피소드).
- `app/runtime/episode_query.py` — 에피소드 하이브리드 조회 + raw 드릴다운.

변경:
- `app/config.py` — `redis_url` 추가, `use_redis` 게이트.
- `app/runtime/repository.py` — `save_episode` / `query_episodes` / `get_episode` 를 Protocol·InMemory·Elastic 세 구현에 추가. `agent_episodes` 인덱스 상수.
- `app/orchestration/committer.py` — per-turn commit → "Redis 매 턴 + ES 체크포인트" write-back으로 리팩터.
- `app/orchestration/workflow.py`, `phases.py` — 체크포인트 트리거(phase 경계, approve/reject/backtrack) 삽입.
- `app/runtime/thread_store.py` — `ThreadRecord.state`를 hot_store 캐시로 다루도록 로드/세이브 경로 조정(프로세스 캐시는 유지, 진실은 Redis→ES).
- `pyproject.toml` — `redis>=5,<6` (optional, `use_redis` 시에만 import).

Java(`backend/`)는 §4 에피소드 writer 결정에 따라 변경 여부 결정.

## 2. Redis 핫 티어

### 2.1 키 스키마

```
lp:rt:{thread_id}:state   -> SharedStateVector JSON (live)
```

- `thread_id`로 키잉한다. Elastic `agent_thread_states`의 doc id가 곧 `thread_id`라 미러된다. scope(`workspace_id`+`campaign_id`)는 저장 값(`SharedStateVector.scope`) 안에 함께 산다. (구현: `app/runtime/hot_store.py`)
- `compact_lessons`는 `SharedStateVector` 안에 이미 있으므로 상태 1개로 같이 산다(핫 lessons 별도 키 불필요).
- TTL = 24h (`agent_thread_states` retention과 일치, contract 07).
- 값은 `SharedStateVector.model_dump(mode="json")` 그대로. `revision` 포함.

### 2.2 인터페이스 (`hot_store.py`)

```python
class HotStateStore(Protocol):
    async def get_state(self, scope: ScopeContext) -> SharedStateVector | None: ...
    async def put_state(self, scope: ScopeContext, state: SharedStateVector) -> None: ...
    async def drop_state(self, scope: ScopeContext) -> None: ...

class RedisHotStore:   # redis.asyncio, settings.redis_url
class InMemoryHotStore:  # dict, 오프라인/테스트 (repository.py의 memory 폴백과 동일 패턴)

def get_hot_store() -> HotStateStore:  # use_redis면 Redis, 아니면 InMemory
```

오프라인 폴백을 두는 이유: 현재 repo가 ES/LLM 없이도 전체 동작하는 2모드(`use_real_*`)를 유지하기 때문. Redis도 같은 규칙을 따른다.

### 2.3 rehydrate (authoritative = ES)

매 턴 상태 로드 순서:
1. `hot_store.get_state(scope)` — hit면 사용.
2. miss면 `repository.load_state(thread_id)` (ES `agent_thread_states`) → 없으면 최신 에피소드 `state_snapshot`에서 복원 → `hot_store.put_state`.
3. 둘 다 없으면 신규 `SharedStateVector(scope=scope)`.

불일치 시 항상 ES가 진실. Redis는 ES에서 재구성 가능한 전제로만 읽는다(ADR-005 Risk 1/6).

## 3. 에피소드 모델 + `agent_episodes`

### 3.1 모델 (`episode.py`)

```python
class EpisodeOutcome(str, Enum):
    FORWARD = "forward"     # phase 경계 정상 전진
    APPROVE = "approve"
    REJECT = "reject"
    BACKTRACK = "backtrack" # 폐기/회귀 (실패도 기록)

class StateSnapshot(BaseModel):       # 복원용 (Risk 3: 필수)
    current_phase: PhaseType
    target_phase: PhaseType
    phase_artifact_refs: dict[str, list[str]]
    key_params: dict[str, Any]        # metric/threshold 등 핵심 파라미터
    revision: int

class Episode(BaseModel):
    episode_id: str
    workspace_id: str
    campaign_id: str
    thread_id: str
    phase: PhaseType
    outcome: EpisodeOutcome
    run_id: str | None                # obsolete 필터용 태그
    raw: list[dict[str, str]]         # 직전 적재~이 사건 구간 대화
    summary: str | None = None        # MVP 보류 (None)
    embedding: list[float] | None = None  # MVP 보류 (None)
    state_snapshot: StateSnapshot     # checkpoint
    created_at: float
```

### 3.2 인덱스 / 계약

- 인덱스 `agent_episodes` 신설. contract 07에 인덱스 정의 추가(아래 §6 계약 변경).
- append-only. 매핑: `summary`/`raw`는 text, `embedding`은 dense_vector(MVP는 미사용이라 매핑만 예약 또는 추후 추가). 필터 필드(`workspace_id`,`campaign_id`,`thread_id`,`phase`,`outcome`,`run_id`)는 keyword, `created_at` date.
- retention: `agent_state_deltas`와 동급(7일) 또는 데모 리셋 경계. checkpoint·감사용이라 state/artifact(24h)보다 길게.

### 3.3 EpisodeBuilder

직전 체크포인트 이후 누적된 대화 버퍼(현재 `active_chat_history` 또는 별도 turn 버퍼)와 현재 `SharedStateVector`로 `Episode`를 만든다. MVP: `raw` + `state_snapshot`만 채우고 `summary`/`embedding`은 `None`.

## 4. 적재 트리거 (write-back 체크포인트)

`committer.py`를 다음으로 리팩터한다.

매 턴(모든 accepted transition):
- `hot_store.put_state(scope, state)` — Redis 라이브 갱신(빠름).
- `repository.append_delta(event)` — `agent_state_deltas` append (감사·Phoenix 상관, write-only 저렴). *상태 스냅샷은 매 턴 ES에 쓰지 않는다.*

체크포인트(주 트리거):
- phase 경계 전진(FORWARD), 결정 사건(APPROVE/REJECT/BACKTRACK).
- 동작: ① `repository.commit_state`(OCC)로 `agent_thread_states` 스냅샷 ② `EpisodeBuilder` → `repository.save_episode`로 `agent_episodes` 적재 ③ 버퍼 리셋.

보조 트리거(안전망):
- 직전 체크포인트 이후 N턴/바이트 초과(버퍼 임계), 세션 종료. → 강제 체크포인트.

손실 모델: 체크포인트 사이 crash = 미완성 진행분만 손실. FAILED 재시작 + Java 세션 리플레이로 대화 재구동(ADR-0002/0008). 현재의 per-turn AGENT_BUSY 충돌 처리(committer)는 체크포인트 commit_state에서 그대로 유지.

트리거 위치: phase 전진과 결정 사건은 `workflow.py`/`phases.py`가 이미 분기하는 지점이므로, 그 자리에 `checkpoint(turn)` 호출을 추가한다.

## 5. 조회 (`episode_query.py`)

```python
async def query_episodes(
    scope, *, phase=None, outcome=None, run_id=None,
    query_text=None, k=5,
) -> list[Episode]: ...

async def get_episode(episode_id) -> Episode | None: ...  # raw 드릴다운(2단계)
```

- 하드 필터(절대 안 넘김): `workspace_id` + `campaign_id` [+ `phase`/`outcome`/`run_id`].
- **MVP**: 필터 + `created_at` desc(recency) + `size=k`. raw 그대로 반환·주입. (LLM 요약·임베딩 보류 — ADR-005 C6.)
- **목표(추후)**: 위 필터 위에 kNN 임베딩 유사도 + recency 부스트로 하이브리드 top-k → `summary` 우선 주입 → 필요 시 `get_episode`로 raw 페이지인(MemGPT 2단계).
- 조회자 = Python read-only. 하이브리드는 ES 강점 그대로(ADR-0001).
- obsolete 제외: 현재 `run_id`로 필터(폐기 forward는 append-only로 남기되 조회에서 뺌).

`query_text`/임베딩 파라미터는 인터페이스에 미리 두되 MVP 구현에서는 무시 → 추후 토글로 활성화(코드 변경 최소).

## 6. 회귀 (rerun / restore)

상태 변이는 Redis, 사건 기록은 ES 에피소드. 두 층 분리(ADR-005 §2 회귀).

### 6.1 재실행 (rerun) — 주 케이스
기존 reducer가 이미 BACKTRACK 상태 변이를 한다(`transitions.py`). 추가할 것:
- 변이 직후 backtrack 에피소드 적재(`outcome=BACKTRACK`, 폐기 artifact ref, `state_snapshot`).
- 재실행 worker 입력에 `compact_lessons`(Redis) + 관련 과거 에피소드 top-k(`query_episodes`) 결합. 옛 원문·폐기 artifact는 제외(bloat 차단). 피드백 주입은 기존 Stage 2.5 경로 재사용.

### 6.2 복원 (restore) — 지원 케이스
- 신규 의도 처리: target revision/에피소드로 복원.
- `query_episodes(scope, phase=..., run_id=...)` 또는 episode_id로 대상 phase 에피소드 로드.
- `state_snapshot`으로 `SharedStateVector` 재구성 → `hot_store.put_state` → ES `commit_state`로 새 revision 고정.
- 복원은 lessons로 불가(lossy)하므로 `state_snapshot` 필수(Risk 3). 적재 시 스냅샷 누락을 막는 가드.

## 7. 단계별 구현 계획

- **Phase 1 — Redis 핫 티어:** `hot_store.py` + config + `committer`/`workflow`가 live 상태를 Redis에 read/write. ES는 일단 기존 per-turn commit 유지(안전). 오프라인 InMemoryHotStore로 테스트 그린 유지. → live 성능(R1) 확보, 동작 불변.
- **Phase 2 — 에피소드 적재:** `episode.py` + `repository.save_episode` + `agent_episodes` 매핑/계약. 체크포인트 트리거로 적재. per-turn state commit → 체크포인트 write-back으로 전환(deltas는 per-turn 유지).
- **Phase 3 — 조회:** `episode_query.py` MVP(필터+recency+raw). 재실행 worker 입력에 과거 에피소드 top-k 주입.
- **Phase 4 — 복원:** restore 의도 + `state_snapshot` 재구성 경로.
- **Phase 5 — 고도화(추후):** LLM 요약·임베딩 + 하이브리드 top-k 토글, Java 에피소드 writer(아래 결정에 따라), obsolete run cancellation.

각 Phase는 독립 그린 테스트로 닫는다(기존 42개 + 신규).

## 8. 확정된 결정 (2026-06-11)

1. **에피소드 ES writer = Java.** Python은 에피소드 내용 생성 + persist 신호만, ES write는 Java가 수행한다(ADR-005 C4 정합). Python→Java 신호는 contract 02(java-python-agent) 경로로 Phase 2에서 정의한다. 2주체 조율(Risk 7)은 persist 신호 + ack로 방어.
2. **Redis 인프라 = compose에 추가.** `docker-compose.yml`에 `redis` 서비스 추가 완료, agent에 `REDIS_URL=redis://redis:6379/0` 주입. `REDIS_URL` 미설정 시 `InMemoryHotStore` 폴백(오프라인/테스트).
3. **delta 적재 = per-turn append 유지.** `agent_state_deltas`는 매 턴 append(감사·Phoenix 상관). 상태 스냅샷·에피소드만 체크포인트 write-back.

## 9. 구현 진행 상태

- **Phase 1 (완료):** Redis 핫 티어. `app/runtime/hot_store.py`(`HotStateStore`/`InMemoryHotStore`/`RedisHotStore`), `config.py`(`redis_url`/`use_redis`), `pyproject.toml`(`redis>=5`). turn load는 hot-first(`context.py` `LoadPersistedState`), commit 시 hot 갱신(`committer.py`). `docker-compose.yml` redis 서비스. 테스트 `tests/test_hot_store.py`(5케이스). ES per-turn commit은 Phase 1에서 유지(안전). 전체 13 pass.
- **Phase 2 (완료):** 에피소딕 적재. `app/runtime/episode.py`(`Episode`/`StateSnapshot`/`build_episode`), `repository.py`(`save_episode`/`query_episodes`/`get_episode` + `agent_episodes` 인덱스, InMemory+Elastic), `orchestration/checkpoint.py`(`Checkpointer` — phase 경계/approve/reject/backtrack 시 적재), `workflow.py` 훅. contract 07 `agent_episodes` 정의. writer는 interim Python(ADR C4 Java는 Phase 5).
- **Phase 3 (완료):** 조회. `app/runtime/episode_query.py`(`recent_episode_context` — 하드필터+recency, compact only). `workers.py` 3워커에 `memory_context` 옵션 파라미터, `phases.py`가 phase별 과거 에피소드 주입. raw 드릴다운/요약/임베딩은 보류(MVP).
- **Phase 4 (완료):** 복원. `app/runtime/restore.py`(`restore_from_episode` — snapshot으로 phase/refs/artifacts 재구성, revision 비롤백). `router.py` `_restore` 훅(BACKTRACK + `mutation.restore_episode_id`). interpreter 트리거 학습은 Phase 5.
- **테스트:** `tests/test_hot_store.py`(5) + `tests/test_episode.py`(8) + 기존 = 20 pass.
- **Phase 5 (미착수):** LLM 요약·임베딩 + 하이브리드 kNN, Java 에피소드 writer(contract 02 신호), restore interpreter 의도, obsolete run cancellation.
