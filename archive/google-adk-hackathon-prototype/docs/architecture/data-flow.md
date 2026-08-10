# LaunchPilot 데이터 흐름

> 누가 누구에게 어떤 데이터를 보내는지 한 장으로. 수정 잦은 문서 — 표/블록 단위로 고치면 됨.
> 출처: 코드 기준 (contracts/01, 02, 05 + backend + apps/agent). 추측 아님.

---

## 1. 구성요소

```
┌──────────┐   HTTP+WS    ┌──────────┐   HTTP+WS    ┌──────────┐
│ Frontend │ ───────────> │   Java   │ ───────────> │  Python  │
│ Next.js  │ <─────────── │  :8080   │ <─────────── │  :8000   │
└──────────┘    blocks    └────┬─────┘    blocks    └────┬─────┘
                               │ REST/ES                 │ MCP(opt)
                               ▼                         ▼
                          Elasticsearch            Elastic MCP
                             :9200                  (stub 가능)
```

| 컴포넌트 | 역할 | 상태 저장 |
|---|---|---|
| Frontend | UI. Java만 호출 (Python 직접 못 봄) | 브라우저 로컬 상태 |
| Java | 중계자 + 게이트키퍼 + 불변 쓰기 | 인메모리(thread→ws/camp, 타임라인, 게이트) + Elastic |
| Python | AI 두뇌. Orchestrator Component가 자유 대화를 `StateDeltaProposal`로 해석하고 reducer/delegation을 수행 | 인메모리 block timeline + Elastic runtime repository |
| Elastic | business data + runtime coordination 저장소 | content_posts / growth_briefs / calendar_events / agent_thread_states / agent_state_deltas / agent_runtime_artifacts / agent_thread_messages |

포트 주의: FE 기본 `NEXT_PUBLIC_AGENT_API_BASE_URL`이 `:8090`인데 Java는 `:8080`. env로 맞춰야 함.

---

## 2. 3가지 흐름

### 흐름 ① CSV Import (HTTP, 단발)

```
FE ──POST /api/import/csv (multipart)──> JAVA ──bulk index──> ES.content_posts
FE <──201 ImportCsvResponse──────────────  JAVA
                                           registry.put(threadId → {ws, camp})
```

| 방향 | 형식 | 핵심 필드 |
|---|---|---|
| FE→Java | `multipart/form-data` | `file`, `workspace_id`, `campaign_id`, `source_platform` |
| Java→FE | `ImportCsvResponse` | `import_id`, `indexed_count`, `failed_count`, `columns[]` |

`import_id` → FE가 `threadId = thread_<import_id의 imp_ 제거>` 생성.

### 흐름 ② 분석/채팅 (WebSocket, AI 경유)

```
FE ──WS open──> JAVA ──WS open──> PY
FE ──message.send {content}──> JAVA ──POST /turns──> PY
                               JAVA <──202──────────  PY
FE <──blocks──── JAVA <──InternalStreamMessage(WS)── PY (파이프라인 실행)
```

| 방향 | 형식 | 핵심 필드 |
|---|---|---|
| FE→Java | `message.send` (WS) | `command_id`, `thread_id`, `content`, `action?` |
| Java→PY | `InternalAgentTurn` (REST) | `thread_id`, `workspace_id`, `campaign_id`, `content` |
| PY→Java | `InternalStreamMessage` (WS) | `id`, `sequence`, `role`, `blocks[]` |
| Java→FE | `StreamMessage` (WS) | 동일 (timeline 거쳐 broadcast) |

### 흐름 ③ 승인/거절 (WebSocket, ★Python 안 감)

```
FE ──message.send {action:approve, payload}──> JAVA ──writes──> ES.growth_briefs
FE <──result block──────────────────────────── JAVA            ES.calendar_events
```

| 방향 | 형식 | 핵심 필드 |
|---|---|---|
| FE→Java | `message.send` + `action` | `action.name`, `action.target_id`, `action.payload.final_experiments` |
| Java→FE | `result` block | `approval_result.growth_brief_id`, `created_calendar_events[]` |

규칙: `action`(approve/reject/cancel/revise) = Java 결정론, Python 미경유. `content`만 = Python(AI).

---

## 3. 흐르는 데이터 = "블록" (7종, 계약 01=02 동일)

PY가 만들어 FE까지 그대로 흐름.

| kind | 만드는 곳 | 필드 | FE 표시 |
|---|---|---|---|
| `text` | agent | `text` | 말풍선 |
| `activity` | 도구 호출 | `id`, `title`, `status`, `detail?` | 글래스박스 카드 |
| `markdown_document` | 근거 문서 | `id`, `title`, `markdown`, `summary?` | 우측 패널 |
| `artifact` | signal/hyp/plan | `id`, `artifact_kind`, `title`, `content` | 카드 |
| `approval` | 게이트 | `id`, `target_id`, `actions[]`, `payload` | 승인 버튼 |
| `result` | 완료 | `title`, `detail`, `approval_result?` | 완료 배너 |
| `error` | 실패 | `title`, `detail`, `retryable` | 에러 배너 |

---

## 4. Python Orchestrator Component — 턴 처리 ★

`content`가 들어오면 Python은 UI가 넘긴 phase command를 신뢰하지 않고, 자유 대화에서 상태 변경 후보를 추출한다.

```
turn
  -> resolve ScopeContext(workspace_id, campaign_id, thread_id)
  -> bounded load(campaign context, thread state, recent messages, runtime refs)
  -> Turn Interpreter: StateDeltaProposal
  -> deterministic reducer: SharedStateVector + ReducerDecision
  -> delegation policy: direct reply | phase delegation facade | pipeline rerun
  -> commit runtime state/delta with optimistic revision
```

Scope 규칙:

- `workspace_id`: tenant/data boundary. no-login MVP에서는 `demo_workspace` 기본값 가능.
- `campaign_id`: primary working context. 분석/역주행 agent work에는 필요하다.
- Python은 `agent_thread_messages`를 read-only memory source로 사용한다. 기본 writer는 Java다.
- Python은 승인 전 후보를 business document로 쓰지 않는다. 다만 runtime-only TTL artifact snapshot/ref는 `agent_runtime_artifacts`에 저장할 수 있다.

## 5. Python 파이프라인 — 워커별 입출력 ★

`StateDeltaProposal -> reducer` 결과가 rerun이면 `target_phase`부터 4단계 파이프라인을 실행한다. 각 단계 = LLM 워커(real) 또는 stub(offline).

```
content ─> [analyst] ─> signals ─> [strategist] ─> hypotheses ─> [writer] ─> plan
                                                                              │
                                          [reviewer] <── formatter.assemble <─┘
                                              │ pass → approval block (payload)
                                              │ fail → 해당 워커로 백트래킹
```

### 워커 1: Analyst (신호 탐지)
| 항목 | 내용 |
|---|---|
| 입력 | `content` (사용자 요청) + `date_range` (자동 합성: 최근 7일) |
| 도구 | `query_metric_baseline`, `search_content_posts` |
| 출력 | `SignalDraftOutput { signals: Signal[] }` (최소 1개) |
| emit 블록 | `activity`(도구) + signal별 `text`+`artifact` |

도구 반환: `query_metric_baseline` → `{ok, current_value, baseline_value, lift_ratio, evidence_refs[]}`

### 워커 2: Strategist (가설 생성)
| 항목 | 내용 |
|---|---|
| 입력 | `content` + 앞 단계 `signals[]` |
| 도구 | `search_team_notes` |
| 출력 | `HypothesisDraftOutput { hypotheses: Hypothesis[] }` (최소 1개) |
| 규칙 | 각 가설은 기존 signal id 1개 이상 참조. 저신뢰면 caveat 필수 |

### 워커 3: Writer (실험안 작성)
| 항목 | 내용 |
|---|---|
| 입력 | `content` + `date_range` + `hypotheses[]` |
| 도구 | 없음 (순수 생성) |
| 출력 | `ExperimentPlanDraftOutput { experiment_plan: ExperimentPlan }` |
| 규칙 | 각 실험은 기존 hypothesis id 참조 |

### 게이트: Reviewer (검증, LLM 아님)
| 항목 | 내용 |
|---|---|
| 입력 | `formatter.assemble(signals, hypotheses, plan)` = `AgentResultPayload` |
| 처리 | 결정론 검증 (id 정합성, 필수필드, caveat). LLM이 못 뒤집음 |
| 출력 | `ValidationReport { passed, severity, issues[], retry_instruction }` |
| 실패 시 | `failure.route(issue codes)` → 근본원인 워커부터 재실행 (성공 prefix 재사용) |

issue → 워커 매핑: 플랜 문제=writer, 추론/claim=strategist, 근거 hallucination=analyst.

---

## 5. 도메인 객체 형식 (참조)

### Signal
```json
{"id":"sig_*","type":"performance_spike","title":"...","description":"...",
 "metric_name":"save_rate","current_value":0.12,"baseline_value":0.05,
 "lift_ratio":2.4,"date_window":{"start":"...","end":"..."},
 "confidence":"high","evidence_refs":["post_*",...]}
```

### Hypothesis
```json
{"id":"hyp_*","signal_ids":["sig_*"],"statement":"...","rationale":"...",
 "confidence":"medium","supporting_evidence_refs":[...],"caveats":[...]}
```

### ExperimentItem
```json
{"id":"exp_*","hypothesis_id":"hyp_*","title":"...","channel":"tiktok",
 "content_format":"...","hook":"...","cta":"...","target_metric":"save_rate",
 "success_criteria":"...","scheduled_at":"...","production_brief":"..."}
```

### AgentResultPayload (최종, approval block의 payload)
```json
{"signals":[Signal,...],"hypotheses":[Hypothesis,...],
 "experiment_plan":{"id":"plan_*","summary":"...","overall_confidence":"...",
                    "items":[ExperimentItem,...]}}
```

---

## 6. 실제 페이로드 예시 (hop별)

**FE→Java `message.send`** (분석)
```json
{"command_id":"cmd_message_abc","type":"message.send",
 "thread_id":"thread_20260601_001","content":"분석해줘",
 "client_created_at":"2026-06-01T16:31:00+09:00"}
```

**Java→PY `InternalAgentTurn`** (POST /internal/agent/turns)
```json
{"thread_id":"thread_20260601_001","workspace_id":"demo_workspace",
 "campaign_id":"camp_comeback_teaser","content":"분석해줘",
 "attachments":[],"client_created_at":"...","trace_context":null}
```
> Java가 `trace_context:null` 보냄 → Python inbound 관대 수용 (계약은 required지만 정렬 필요).

**PY→Java `InternalStreamMessage`** (WS, 예: activity)
```json
{"id":"msg_a1b2","thread_id":"thread_20260601_001","sequence":4,
 "role":"assistant","created_at":"...",
 "blocks":[{"kind":"activity","id":"query_metric_baseline",
            "title":"Checked metric baseline","status":"done"}]}
```

**PY→Java approval block** (게이트 — Java가 payload 추출)
```json
{"kind":"approval","id":"appr_xyz","title":"Approve experiment plan",
 "target_id":"plan_001","actions":["approve","reject","request_changes"],
 "payload":{AgentResultPayload}}
```

**FE→Java approve**
```json
{"command_id":"cmd_approve_x","type":"message.send","thread_id":"thread_...",
 "content":"Approve this experiment plan.",
 "action":{"name":"approve","target_id":"appr_xyz",
           "payload":{"final_experiments":[ExperimentItem,...]}}}
```

**Java→FE result block**
```json
{"kind":"result","title":"Approval complete","detail":"...",
 "approval_result":{"approval_id":"appr_xyz","growth_brief_id":"brief_...",
   "created_calendar_events":[{"event_id":"cal_*","title":"...","scheduled_at":"..."}],
   "persisted_at":"..."}}
```

---

## 7. 한눈 시퀀스

```
[Import]   FE ──CSV──> JAVA ──> ES(content_posts)
           FE <──ImportCsvResponse── JAVA

[Connect]  FE ──WS──> JAVA ──WS──> PY

[Analyze]  FE ──message.send(content)──> JAVA ──POST /turns──> PY
           FE <──blocks── JAVA <──stream── PY
                          (analyst→strategist→writer→reviewer)

[Approve]  FE ──message.send(action)──> JAVA ──> ES(growth_briefs, calendar_events)
           FE <──result block── JAVA          (★ PY 미경유)
```

---

## 변환 요약표

| hop | 입력 | 변환 | 출력 |
|---|---|---|---|
| FE→Java import | multipart CSV | parse + bulk | ContentPostDoc → ES |
| Java→FE import | - | - | ImportCsvResponse |
| FE→Java msg | message.send | echo + 라우팅 | user block / turn |
| Java→PY | InternalAgentTurn | - | 202 |
| PY 내부 | content | 4-워커 | AgentResultPayload |
| PY→Java | InternalStreamMessage | passthrough | StreamMessage |
| Java→FE | StreamMessage | timeline+broadcast | block |
| FE→Java approve | action+payload | 결정론 + 쓰기 | ES 불변 쓰기 + result block |
