# [ADR-005] 런타임 메모리 적재·조회: Redis 핫 상태 + Elastic 에피소딕 영속

- **상태(Status):** 제안됨(Proposed)
- **날짜(Date):** 2026년 6월 11일
- **컨텍스트:** Google ADK Python 2.x, Gemini Flash 계열, 단일 Elastic Cloud Serverless, conversation-first Java <-> Python 계약, no-login MVP. 본 ADR은 ADR-004(상태 반응형 워크플로우)·ADR-0001(단일 저장소)·ADR-0002(4계층 기억)·`contracts/07-agent-runtime-elastic` 위에서, 런타임 메모리를 "어디에 적재하고 어떻게 조회하느냐"의 물리 계층(Redis/Elastic)과 에피소딕 수명 정책을 정의한다.

## 1. 요구사항 및 제약사항(Requirements & Constraints)

### 비즈니스 및 UX 요구사항

- **R1. live 상태 고속 접근:** `SharedStateVector`는 매 턴 읽고 쓴다. 턴마다 영속 저장소를 왕복하고 상태를 재조립하면 지연이 커진다. live 상태는 hot 접근이 필요하다.
- **R2. 에피소딕 연속성:** phase 경계와 결정 사건 같은 의미 단위의 대화를 에피소드로 남겨 이어지는 턴과 재실행의 자산으로 쓴다. 실패(backtrack/reject)도 보존해 같은 실수의 반복을 막는다.
- **R3. 비선형 회귀 지원(ADR-004 R3 연계):** 사용자는 ① 조건을 바꿔 재실행하거나 ② 과거 시점으로 상태를 복원할 수 있어야 한다. 두 동작 모두 데이터로 뒷받침되어야 한다.
- **R4. 콘텍스트 무결성(ADR-004 C3 연계):** 조회 시 load-all을 금지한다. 필요한 것만 얇게 주입하고 raw bloat를 차단한다.

### 기술적 제약사항(Technical Constraints)

- **C1. 단일 진실 원천(ADR-0001):** Elastic이 유일한 영속·진실·복구 저장소다. 추가 인프라는 휘발성 coordination/cache로만 정당화하며, 진실 원천이 되어선 안 된다.
- **C2. authoritative = Elastic:** live 상태의 거처가 Redis라도, 충돌과 복구의 권위는 ES가 갖는다. 불일치 시 ES가 이긴다.
- **C3. 결정적 권한(ADR-004, ADR-0006):** 상태 변이와 전이는 reducer가 수행한다. LLM은 적재 내용과 의도를 제안만 한다.
- **C4. 쓰기 주체 경계(ADR-0002, contract 07):** 영속 ES write는 Java가 수행한다. Python은 내용 생성과 persist 신호, 그리고 read-only 조회만 담당한다. 승인된 business document는 승인 시 Java가 쓴다.
- **C5. 데이터 경계:** 모든 적재·조회에 `workspace_id` + `campaign_id`를 동반한다(하드 필터). `campaign_id` 단독을 격리키로 쓰지 않는다.
- **C6. MVP 단순성:** LLM 요약·임베딩 파이프라인은 보류할 수 있다. 초기에는 raw 전체로 시작하고, 에피소드 누적이 콘텍스트를 위협할 때 top-k·요약·임베딩을 켠다.

## 2. 기술적 대안 후보(Technical Alternatives)

세 대안 모두 `SharedStateVector`(live 상태)와 에피소드(과거 사건)를 어디에, 언제 적재하고 어떻게 조회할지를 다르게 푼다. 상위 기준은 단일 진실 원천(C1), authoritative=ES(C2), 콘텍스트 무결성(R4/C3)이다.

### Alternative A: Elastic 단일 + per-turn 적재 (현행 contract 07 연장)

- **구조:** Redis를 두지 않는다. `SharedStateVector`를 매 턴 `agent_thread_states`에서 읽고, 갱신 후 다시 쓴다. 에피소드 개념 없이 state/delta만 유지한다.
- **동작:** 턴마다 ES read -> reduce -> ES write(OCC). 조회는 state 스냅샷 로드가 전부다.
- **한계:** 매 턴 ES 왕복과 상태 재조립으로 지연이 쌓인다. 에피소딕 회귀(재실행 힌트·복원점) 모델이 없어 과거 사건을 자산화하지 못한다. 조회가 state 위주라 "save_rate 관련 과거" 같은 의미 검색이 불가능하다.

### Alternative B: Redis 단일 핫 메모리 (영속 에피소드 없음)

- **구조:** live 상태와 에피소드를 모두 Redis에 둔다. ES는 승인된 business document만 보관한다.
- **동작:** 모든 읽기/쓰기가 Redis라 가장 빠르다.
- **한계:** 휘발이다. eviction이나 재시작 시 복원이 불가능하다(checkpoint 부재). 감사와 회귀 기록이 소실된다. 진실 원천이 Redis가 되어 C1/C2가 붕괴한다. 하이브리드(필터+벡터) 검색은 ES의 강점인데 활용하지 못한다.

### Alternative C: Redis 핫 상태 + Elastic 에피소딕 영속 2계층 -- 채택안

- **구조:**
  - **Redis(핫, 휘발):** live `SharedStateVector` + 핫 `compact_lessons`. 매 턴 read/write하고 `revision`을 증가시키는 working copy.
  - **Elastic(영속, 진실):** 에피소드 append-only. 에피소드 1개 = `{raw 대화구간 + 요약 + 임베딩 + 상태스냅샷(phase/refs/핵심 파라미터/revision) + outcome + run_id}`. authoritative이자 복구점이다.
- **동작 — 적재:** 타이머가 아니라 의미 단위가 끝났을 때 적재한다. 주 트리거 = phase 경계, 결정 사건(approve/reject/backtrack). 보조 트리거(안전망) = 세션 종료, 버퍼 임계(N턴/크기). 에피소드 = 직전 적재 이후부터 이 사건까지의 대화 한 묶음. Python이 내용을 생성하고 persist 신호를 보내면 Java가 ES write를 수행한다(no refresh 벌크).

```text
[적재] 사건 발생 (phase 경계 / approve / reject / backtrack)
  -> Python: 에피소드 내용 결정 (요약/임베딩은 MVP 보류, 상태스냅샷 포함) + persist 신호
  -> Java:   ES write (raw 구간 + [요약/임베딩] + 상태스냅샷 + outcome + run_id), no refresh 벌크
  보조 안전망: 세션 종료 / 버퍼 임계 도달 시에도 flush
```

- **동작 — 조회:** load-all을 금지한다. 하이브리드 top-k = 하드 필터(`workspace_id` + `campaign_id` [+ phase/outcome/run_id]) + 임베딩 유사도 + recency 부스트 -> top-k(3~5) -> 요약 주입 -> 필요 시 `episode_id`로 raw 드릴다운(MemGPT식 2단계). 조회자는 Python(read-only)이고, 하이브리드 검색은 ES의 강점을 그대로 쓴다(ADR-0001이 ES를 고른 이유).

```text
[조회] phase 시작 / grounding 필요
  -> Python: 하이브리드 쿼리 (하드필터 + 벡터 유사도 + recency) -> top-k(3~5)
  -> 1단계: 요약 주입 (raw 아님)
  -> 2단계: LLM이 디테일 필요 시 episode_id로 raw 페이지인 (드릴다운 tool)
```

- **동작 — 회귀:** 두 층의 동작으로 분리한다. 상태 변이(실제 되돌림)는 Redis, 사건 기록(왜·무엇을 버렸나)은 ES 에피소드.

```text
[회귀 - 재실행] 예: EXPERIMENT_PLAN 중 "분석 다시, threshold 1.3"
  1. Python: StateDelta {backtrack, target=DATA_ANALYSIS, mutation=1.3} (제안만)
  2. reducer: Redis 상태 변이 (current_phase<-DATA_ANALYSIS, revision++, active_run_id<-new,
              compact_lessons += "2.0 신호부족 -> 1.3")
  3. Java:  backtrack 에피소드 ES 적재 (outcome=backtrack, 폐기 artifact ref)  <- 실패도 기록
  4. Python analyst 재실행: 입력 = 신규요구(1.3) + lessons(Redis) + scoped evidence(ES read)
              + 관련 과거 episode top-k(ES read).  옛 분석 원문/폐기 plan은 제외(bloat 차단)
  5. 전진 재개 -> phase 경계 -> 분석 에피소드 적재

[회귀 - 복원] 예: "1.3 별로, 아까 2.0 가설로 되돌려"
  1. 의도: restore, target = rev2 에피소드
  2. ES read: rev2 phase 에피소드 로드 (요약 + raw + 상태스냅샷)
  3. Redis 재구성: 그 에피소드 스냅샷으로 상태 복원 (phase/refs/파라미터/revision)
  4. 전진 재개
  -> phase 경계 에피소드가 곧 checkpoint. 별도 checkpoint store 불필요.

[obsolete] 폐기된 forward 에피소드는 삭제하지 않는다(append-only).
           옛 run_id 태그가 붙고, 조회 시 현재 run_id 필터로 제외. 감사 이력으로는 보존.
```

- **핵심 원칙:** authoritative는 ES, Redis는 휘발 working copy다. 적재는 write-back(체크포인트 기반)이며, 체크포인트 사이의 crash 손실은 FAILED 재시작으로 감수한다(ADR-0002의 "런 메모리는 휘발, 죽으면 재시작" 모델 그대로). 대화 자체의 안전망은 Java 세션 + WebSocket 리플레이(ADR-0008)다. 에피소드가 곧 checkpoint이므로 별도 checkpoint store가 필요 없다.
- **MVP 전략:** LLM 요약·임베딩은 초기 보류한다. 적재는 raw + 상태스냅샷만 저장하고, 조회는 하드 필터 + recency + raw 전체로 시작한다. 에피소드 누적이 콘텍스트 무결성(C3)을 위협하는 시점에 top-k·요약·임베딩을 활성화한다.

## 3. 기술별 트레이드오프 분석(Trade-off Analysis)

| 평가 항목 | Alternative A: ES 단일 per-turn | Alternative B: Redis 단일 핫 | Alternative C: Redis 핫 + ES 에피소딕 |
|---|---|---|---|
| **R1: live 상태 접근 지연** | **중간(Marginal)**. 매 턴 ES read/write 왕복과 재조립으로 지연이 쌓인다. | **우수(Excellent)**. 모두 메모리 접근이라 가장 빠르다. | **우수(Good)**. live는 Redis 핫 접근, 영속 write만 체크포인트에 몰아 친다. |
| **C1/C2: 단일 진실 원천·authoritative** | **우수(Excellent)**. ES가 단일 진실. | **낮음(Critical)**. 진실이 휘발 Redis가 되어 복구·감사 불가. | **우수(Excellent)**. 진실·복구는 ES, Redis는 휘발 캐시로 한정. 불일치 시 ES 승. |
| **R2: 에피소딕 자산화(재실행/감사)** | **낮음(Poor)**. 에피소드 모델이 없어 과거 사건을 자산화 못 함. | **중간(Marginal)**. 담더라도 휘발이라 감사·재실행 자산이 사라짐. | **우수(Excellent)**. 결정 사건·실패까지 영구 에피소드로 남겨 재실행 힌트로 쓴다. |
| **R3: 회귀 복원(checkpoint)** | **낮음(Poor)**. 복원점이 없다. | **낮음(Critical)**. eviction 시 복원 불가. | **우수(Excellent)**. phase 에피소드 = checkpoint, 읽어서 Redis 재구성. |
| **R4/C3: 콘텍스트 무결성(조회)** | **중간(Marginal)**. state 위주라 의미 검색 약하고 raw 통제 수단이 적다. | **중간(Marginal)**. 하이브리드 검색 부재로 선별 주입이 어렵다. | **우수(Excellent)**. 하이브리드 top-k + 요약 우선 + raw 드릴다운으로 얇게 유지. |
| **운영 복잡도(MVP)** | **우수(Good)**. 가장 단순하나 위 한계가 크다. | **우수(Good)**. 단순하나 정합성·복구 부채가 치명적. | **중간(Marginal)**. Redis 인프라와 2주체 적재 조율 공수. MVP는 요약/임베딩 보류로 완화. |

## 4. 우선순위 가치 위계 및 최종 결정(Value Hierarchy & Decision)

### 우리의 아키텍처 가치 위계

1. **C2: authoritative = Elastic**  
   live 거처가 Redis라도 진실과 복구의 단일 권위는 ES에 둔다. 이것이 단일 저장소 원칙(C1)의 핵심을 지키는 길이다.
2. **C3: 결정적 권한**  
   상태 변이·전이는 reducer가 한다. LLM은 적재 내용·의도를 제안만 한다.
3. **R2/R3: 에피소딕 회귀 자산화와 복원**  
   결정 사건과 실패를 영구 에피소드로 남겨 재실행 힌트와 복원 checkpoint로 쓴다. 이번 결정의 동기다.
4. **R4: 콘텍스트 무결성**  
   조회는 하이브리드 top-k와 요약 우선으로 얇게 유지한다.
5. **R1: live 성능**  
   live 상태를 Redis 핫 접근으로 처리한다. Redis 도입의 명분이다.
6. **C6: MVP 단순성 감수**  
   요약·임베딩 보류와 raw 전체 사용이라는 초기 단순화를 의도적 부채로 받아들인다.

### 최종 결정 사유

- **Alternative A 기각:** 매 턴 ES 왕복으로 live 성능(R1)이 떨어지고, 에피소딕 회귀 모델이 없어 재실행 자산화와 복원(R2/R3)을 만족하지 못한다.
- **Alternative B 기각:** 모든 것이 휘발이라 복원·감사·회귀 기록이 불가능하고, 진실 원천이 Redis가 되어 단일 진실 원천(C1)과 authoritative(C2)가 붕괴한다. ES 하이브리드 검색 강점도 잃는다.
- **Alternative C 채택:** Redis 핫 상태로 성능(R1)을, ES 에피소딕 영속으로 진실·복구·검색(C2/R2/R3/R4)을 동시에 얻는다. authoritative는 ES로 고정하고, write-back으로 성능을 얻되 손실은 의미 단위 적재와 Java 세션 안전망으로 감수한다. 단일 진실 원천 원칙은 "진실 = ES, Redis = 휘발 캐시"로 재정의해 지킨다. MVP는 raw 전체로 시작하는 의도적 부채를 진다.

## 6. 잔재하는 구조적 리스크(Residual Risks)

### Risk 1: Redis-ES 불일치 및 eviction

- **리스크의 본질:** 같은 상태가 Redis(live)와 ES(에피소드 스냅샷) 두 곳에 존재한다.
- **영향:** Redis 증발(eviction/재시작) 시 live 상태가 사라진다.
- **완화책:** 최신 에피소드/스냅샷에서 ES rehydrate한다. authoritative는 ES이며 불일치 시 ES가 이긴다. Redis는 항상 ES에서 재구성 가능한 전제로만 읽는다.

### Risk 2: write-back 손실 윈도우

- **리스크의 본질:** 체크포인트 사이에 아직 적재되지 않은 진행분이 존재한다.
- **영향:** 그 구간에서 crash가 나면 진행 중이던 run의 미완성 작업이 손실된다.
- **완화책:** 의미 단위 적재라 손실은 "완성되지 않은 진행분"에 한정된다. 보조 트리거(버퍼 임계, 세션 종료)가 누적을 막고, 손실 시 FAILED 재시작 + Java 세션 리플레이로 대화를 재구동한다.

### Risk 3: 복원은 lessons로 불가능(lossy)

- **리스크의 본질:** `compact_lessons`는 요약이라 상태를 그대로 되살리지 못한다.
- **영향:** ② 복원 흐름이 lessons만으로는 실패한다.
- **완화책:** 에피소드에 상태스냅샷(phase/refs/핵심 파라미터/revision)을 필수 필드로 둔다. 스냅샷이 없으면 복원이 불가능하므로 적재 시점에 스냅샷을 강제한다.

### Risk 4: obsolete 에피소드 혼입

- **리스크의 본질:** 폐기된 forward 에피소드가 append-only로 남는다.
- **영향:** 조회 시 폐기안이 되살아나 재주입될 수 있다.
- **완화책:** `run_id` 태그를 붙이고 조회 시 현재 `run_id`로 필터링한다. 필터 누락을 막는 가드를 둔다. 감사 이력으로는 보존한다.

### Risk 5: MVP raw 전체 주입으로 인한 bloat

- **리스크의 본질:** 요약·top-k를 보류해 raw가 누적된다.
- **영향:** 에피소드가 늘면 콘텍스트 무결성(C3)이 위협받는다.
- **완화책:** 캠페인 범위 + 에피소드 개수 상한으로 자연 경계를 두고, 임계 초과 시 top-k·요약·임베딩으로 전환한다.

### Risk 6: 단일 진실 원천 원칙 약화

- **리스크의 본질:** Redis라는 두 번째 인프라가 추가된다.
- **영향:** Redis를 진실로 읽는 코드가 생기면 ADR-0001이 무너진다.
- **완화책:** Redis read는 항상 ES rehydrate가 가능한 전제로만 한다. business/evidence query는 Redis를 참조하지 않는다.

### Risk 7: 2주체 적재 조율 실패

- **리스크의 본질:** 내용 생성은 Python, ES write는 Java로 나뉜다.
- **영향:** persist 신호가 유실되면 에피소드가 누락된다.
- **완화책:** persist 신호 + Java ack를 둔다. 신호 실패 시 보조 트리거(버퍼 임계/세션 종료)가 포착한다.
