# LaunchPilot Backend 설계 (Java Business Backend)

상태: 설계 v0.1
범위: C4 `Business Backend (Java 21 / Spring Boot)` 컨테이너 하나
마지막 갱신: 2026-06-02

이 문서는 `contracts/`, `docs/architecture/launchpilot-c4.md`, `scenarios/`를 엄격히(strict) 따른다.
계약과 충돌하는 구현은 버그로 간주한다.

---

## 0. 역할: 연결 중심점 (Hub)

Spring Backend는 3개 외부 경계를 잇는 유일한 중심점이다. 자체 비즈니스 상태는 없고(진실의 원천은 Elastic), ①의 요청을 ②/③ 호출로 번역하고 결과를 ①/③ 모양으로 재포장하는 오케스트레이터다.

```
                     ┌──────────────────────────┐
   Frontend  ──①──>  │                          │
   (Next.js)  <───── │   Spring Business         │ ──②──>  Python Infra
                     │   Backend (HUB)           │ <─────  (FastAPI / ADK Agent)
   Elastic   <──③──> │                          │
   Cloud             └──────────────────────────┘
```

| # | 연결 | 방향 | 계약 | 구현 컴포넌트 |
| --- | --- | --- | --- | --- |
| ① | Frontend ↔ Spring | 인바운드 REST | `01-frontend-java/openapi.yaml` | `api/` + `dto/pub/` |
| ② | Spring ↔ Python | 아웃바운드 RestClient | `02-java-python-agent/openapi.yaml` | `client/AgentServiceClient` + `dto/internal/` |
| ③ | Spring ↔ Elastic Cloud | 아웃바운드 ES Java Client | `03-java-elastic/documents.schema.json` | `client/ElasticDocumentWriter` + `dto/elastic/` |

경계별 책임:
- **① Frontend**: 공개 API만 노출. Python / Elastic / Gemini 직접 노출 금지 (MVP-R3).
- **② Python**: 비동기 트리거 + 폴링 중계 + 승인 시 페이로드 재수집. Java는 추론하지 않고 런 상태도 보관하지 않음 (Python 소유).
- **③ Elastic**: CSV → `content_posts` 색인, 승인 → `growth_briefs` + `calendar_events` append-only 적재. 유일 데이터 저장소.

---

## 1. 설계 원칙 (문서에서 강제되는 규칙)

C4와 계약에서 직접 도출한 불변 규칙. 코드는 이 규칙을 위반할 수 없다.

- **RDB 없음.** Elastic Cloud Serverless가 유일한 데이터 저장소다.
- **순수 게이트웨이.** Java는 추론하지 않는다. CSV 적재, 비동기 에이전트 트리거, 폴링 중계, 승인 영속화만 담당.
- **Java는 런 상태를 보관하지 않는다.** 에이전트 런 상태는 Python이 소유한다. Java는 폴링을 Python으로 중계한다.
- **승인 산출물은 append-only.** 승인된 `growth_briefs` / `calendar_events`는 제자리 수정 금지.
- **승인은 1회성.** 같은 `agent_run_id` 중복 승인은 `409 Conflict`.
- **Elastic 쓰기는 `refresh=true`.** 데모 예측 가능성 확보.
- **승인 벌크 쓰기는 all-or-fail.** 전부 색인 성공해야 200. 하나라도 실패하면 승인 실패로 처리.
- **재시도는 결정적 ID 사용.** 모호한 실패 후 재시도해도 중복 산출물 생성 금지.
- **프론트는 Java 공개 API만 호출.** Java만 Python / Elastic에 접근.

---

## 2. 기술 스택

| 항목 | 선택 | 이유 |
| --- | --- | --- |
| 언어/런타임 | Java 21 | C4 명시 |
| 프레임워크 | Spring Boot 3.x | C4 명시 |
| 빌드 | Gradle (Kotlin DSL) | 가벼운 설정 |
| HTTP 클라이언트 | Spring `RestClient` | Python 내부 호출 |
| Elastic 클라이언트 | Elasticsearch Java Client (`co.elastic.clients`) | 공식 고수준 REST |
| 비동기 | Spring `@Async` + 전용 `TaskExecutor` | Tomcat 스레드 고갈 방지 |
| JSON | Jackson (snake_case, unknown 거부) | 계약 strict 직렬화 |
| 테스트 | JUnit 5 + 실 Elastic Cloud + WireMock(Python 스텁) | e2e 통과 테스트만 |

---

## 3. 데이터 저장소 결정

실(real) Elastic Cloud Serverless를 사용한다.

- 접속 시크릿: 환경변수 `ELASTIC_URL`(또는 `ELASTIC_CLOUD_ID`) + `ELASTIC_API_KEY`. 절대 커밋 금지.
- Python 내부 서비스 주소: `AGENT_SERVICE_URL`.
- 설정 프로파일: `application.yaml`(기본) + `application-e2e.yaml`(테스트).

### 3.1 인덱스 부트스트랩

기동 시 아래 3개 인덱스가 없으면 명시적 매핑으로 생성한다 (동적 매핑 드리프트 방지).

| 인덱스 | 작성자 | 문서 ID | 변경성 |
| --- | --- | --- | --- |
| `content_posts` | `ImportService` | `post_id` | 색인 시 upsert |
| `growth_briefs` | `BusinessDataService` | `growth_brief_id` | append-only |
| `calendar_events` | `BusinessDataService` | `event_id` | append-only |

매핑 핵심:
- 모든 `*_id`, `workspace_id`, `campaign_id`, `channel` → `keyword`
- `published_at`, `scheduled_at`, `approved_at`, `created_at`, `ingested_at` → `date`
- `metrics` → `object` (동적 숫자 필드 허용)
- `signals`, `hypotheses`, `final_experiments` → `object` (스냅숏 저장, 검색 대상 아님)

---

## 4. 폴더 구조

```
backend/
  build.gradle.kts
  settings.gradle.kts
  src/main/java/com/launchpilot/
    LaunchPilotApplication.java
    config/
      JacksonConfig.java          # snake_case, FAIL_ON_UNKNOWN_PROPERTIES
      AsyncConfig.java            # 에이전트 잡 전용 TaskExecutor
      ElasticClientConfig.java    # ES Java Client 빈, 인덱스 부트스트랩
      AgentServiceConfig.java     # Python RestClient 빈, base URL
    api/
      ImportController.java       # POST /api/import/csv
      AgentController.java        # POST /api/agent/run, GET /api/agent/runs/{id}, POST .../approve
      GlobalExceptionHandler.java # -> ErrorResponse
    dto/
      pub/                        # 계약 01 (프론트 <-> Java) 레코드
      internal/                   # 계약 02 (Java <-> Python) 레코드
      elastic/                    # 계약 03 (Java -> Elastic) 문서 레코드
    service/
      ImportService.java          # CSV 파싱 제어 + 벌크 색인
      CsvStreamingParser.java     # OOM 방지 청크 반복자
      IdGenerator.java            # run_ / imp_ / brief_ / cal_ 결정적 생성
      AgentRunService.java        # run_id 생성 + Python 트리거 + 폴링 중계(내부->공개 매핑)
      AgentRunRegistry.java       # run_id -> workspace/campaign 일시 코디네이션 맵
      BusinessDataService.java    # 승인: 페이로드 수집 -> 산출물 빌드 -> 벌크 색인
      ApiException.java           # 도메인 오류 -> HTTP 상태 + 계약 코드
    client/
      AgentServiceClient.java     # Python /internal/agent 호출
      ElasticDocumentWriter.java  # content_posts upsert, briefs+events 벌크
  src/test/java/com/launchpilot/e2e/
    MainAnalysisApprovalE2ETest.java
  src/test/resources/
    application-e2e.yaml
```

C4 컴포넌트(섹션 5, Java Backend Component View)와 1:1 대응:
- `ImportController/ImpService/Parser` = Tier1/2 Import
- `AgentController/AgentAsyncJobManager` = Task Trigger/Polling
- `BusinessController/BusinessDataService` → 본 MVP는 `AgentController`의 approve 액션으로 통합 (별도 BusinessController 불필요)
- `ElasticDocumentWriter` = ES Client (Tier3)

---

## 5. 엔드포인트 매핑 (계약 01 -> 동작)

| 공개 엔드포인트 | 동작 | 외부 호출 | 응답 |
| --- | --- | --- | --- |
| `POST /api/import/csv` | CSV 스트리밍 파싱 -> `content_posts` 정규화 -> 벌크 색인 `refresh=true` | Elastic | `201 ImportCsvResponse` |
| `POST /api/agent/run` | `run_*`+`req_*` 생성, 비동기 `POST /internal/agent/runs` 호출, 즉시 반환 | Python(비동기) | `202 AgentRunAcceptedResponse` (`PENDING`, `next_poll_url`) |
| `GET /api/agent/runs/{id}` | `GET /internal/agent/runs/{id}` 중계, 내부 전용 필드 제거 | Python | `200 AgentRunStatusResponse` |
| `POST /api/agent/actions/{id}/approve` | 내부 페이로드 수집 -> 브리프/이벤트 빌드 -> 벌크 색인 | Python + Elastic | `200 ApproveExperimentPlanResponse` |

### 5.1 내부 -> 공개 상태 매핑 (GET runs)

`InternalAgentRunStatusResponse`(계약 02)에서 공개 응답으로 변환 시 **제거**할 내부 전용 필드:
`agent_diagnostics`, `started_at`, `updated_at`, `completed_at`.

유지: `agent_run_id`, `status`, `current_stage`, `retry_count`, `error_message`, `payload`, `tool_call_logs`.

---

## 6. 시나리오 흐름 (scenarios/main-analysis-approval.scenario.json 기준)

```
1. import_csv          FE -> Java       POST /api/import/csv            201 ok
2. run_agent           FE -> Java       POST /api/agent/run             202 PENDING
   internal_start      Java -> Python   POST /internal/agent/runs       202 PENDING (같은 run_id)
3. poll_running        FE -> Java       GET  /api/agent/runs/{id}       200 RUNNING_EVIDENCE_SEARCH, payload null
   internal_poll_ready Java -> Python   GET  /internal/agent/runs/{id}  200 WAITING_FOR_APPROVAL, payload 존재
4. poll_ready          FE -> Java       GET  /api/agent/runs/{id}       200 WAITING_FOR_APPROVAL, payload 존재
5. approve_plan        FE -> Java       POST /api/agent/actions/{id}/approve  200 ok
   persist_growth_brief    Java -> Elastic   growth_briefs   1건
   persist_calendar_event  Java -> Elastic   calendar_events N건
```

불변(invariants) 강제 지점:
- `agent_run_id`는 공개/내부 생명주기 전체에서 동일 (Java가 생성해 Python에 그대로 전달).
- 공개 `poll_ready` 페이로드 모양 = 내부 ready 페이로드 모양 (필드 제거만, 변형 없음).
- 승인 요청의 `experiment_plan_id` = `poll_ready` 페이로드의 `experiment_plan.id`.
- 승인 응답 `growth_brief_id` = 영속화된 `growth_brief`의 ID.
- `calendar_events`는 승인된 실험을 참조 (`experiment_id`, `growth_brief_id`).

---

## 7. 승인 플로우 상세 (가장 엄격한 구간)

승인 요청(`ApproveExperimentPlanRequest`)은 `experiment_plan_id` + `approved_by` + `final_experiments`만 담는다.
하지만 `growth_briefs` 문서는 `signals`, `hypotheses`, `summary`, `source_evidence_refs`도 요구한다.
따라서 Java는 승인 시 Python에서 페이로드를 다시 가져온다.

순서:
1. `GET /internal/agent/runs/{agent_run_id}` 로 `signals` / `hypotheses` / `experiment_plan.summary` 수집.
2. `status != WAITING_FOR_APPROVAL` → `409` (`code: RUN_*`, 공개는 일반 ErrorResponse).
3. 요청 `experiment_plan_id != payload.experiment_plan.id` → `400 INVALID_REQUEST`.
4. **1회성 검사**: `growth_briefs`에서 `agent_run_id`로 조회. 이미 존재 → `409`.
   - `growth_brief_id`는 `agent_run_id` 기반 결정적 생성 → 재시도 멱등.
5. 문서 빌드:
   - `growth_briefs` 1건: `signals`/`hypotheses`는 페이로드에서, `final_experiments`는 **요청에서** (프론트 사용자 편집 보존), `version: 1`.
   - `calendar_events` N건: `final_experiments[]` 1건당 1개. 각자 `growth_brief_id` 참조.
   - `source_evidence_refs` = signals/hypotheses의 evidence_refs 합집합.
6. 벌크 색인 `refresh=true`, all-or-fail. 부분 실패 → 승인 실패 응답, 성공 주장 금지.
7. `200 ApproveExperimentPlanResponse` (`growth_brief_id`, `created_calendar_events[]`, `persisted_at`).

`workspace_id` / `campaign_id` 출처: 계약 02 내부 상태 응답에는 없다. 런 시작(`POST /api/agent/run`) 시점에 `AgentRunRegistry`(메모리 맵)에 보관한 요청 맥락에서 가져온다. 이는 비즈니스 상태가 아니라 진행 중 런의 일시적 라우팅 정보이며, 진실의 원천은 여전히 Elastic이다. (한계: 프로세스 재시작 시 진행 중 런 맥락 소실 → 데모/단일 인스턴스 가정.)

---

## 8. 계약 strict 준수 메커니즘

| 계약 요구 | 강제 방법 |
| --- | --- |
| `additionalProperties: false` | DTO 레코드에 계약 외 필드 추가 금지 |
| snake_case 필드명 | Jackson `PropertyNamingStrategies.SNAKE_CASE` |
| 알 수 없는 필드 거부 | `FAIL_ON_UNKNOWN_PROPERTIES = true` |
| ID 패턴 (`run_` `imp_` `brief_` 등) | `IdGenerator` 생성 + 입력 정규식 검증 |
| 상태 enum | `AgentRunStatus` enum, 매핑 누락 시 예외 |
| 에러 코드 enum (계약 02) | `INVALID_REQUEST`/`RUN_NOT_FOUND`/`RUN_ID_CONFLICT`/`AGENT_BUSY`/`TOOL_CALL_FAILED`/`GEMINI_FAILED`/`VALIDATION_FAILED`/`INTERNAL_AGENT_ERROR` |
| 에러 응답 모양 | `GlobalExceptionHandler` → `ErrorResponse {ok:false, error:{code, message, request_id}}` |
| HTTP 상태 (201/202/200/400/404/409) | 컨트롤러 + 예외 핸들러에서 명시 |

---

## 9. ID 규칙 (계약 03)

| 접두사 | 대상 | 생성자 |
| --- | --- | --- |
| `imp_` | CSV 임포트 | Java |
| `post_` | content_posts | Java (CSV 행 정규화) |
| `run_` | 에이전트 런 | Java |
| `req_` | trace_context.request_id | Java |
| `brief_` | growth_briefs | Java (agent_run_id 기반 결정적) |
| `cal_` | calendar_events | Java (결정적) |
| `plan_`/`exp_`/`hyp_`/`sig_` | 에이전트 산출물 | Python (Java는 전달/검증만) |

재시도 시 동일 논리 연산은 동일 ID를 생성해야 한다.

---

## 10. e2e 테스트 전략 (유일 테스트)

`scenarios/main-analysis-approval.scenario.json` 흐름을 기동된 Spring 앱에 대해 실행한다.

구성:
- **Python 에이전트** → WireMock (랜덤 포트, 계약 02 픽스처 제공, base URL을 Spring 프로퍼티로 주입).
- **Elastic** → 실 Elastic Cloud Serverless (실제 색인/조회로 영속화 불변 검증).
- 환경변수 `ELASTIC_*` 부재 시 테스트는 graceful skip (크리덴셜 없이 빌드 실패 방지).

테스트 격리 (실 클러스터 오염 방지):
- 매 실행마다 유니크 `workspace_id`/`campaign_id` (타임스탬프+랜덤) → append-only / 1회성 승인 `409`가 재실행 간 깨끗.
- teardown: 해당 workspace 대상 `delete_by_query` (`refresh=true`).

단언(assert):
- import `201`, `indexed_count` 일치, `import_id` 패턴.
- run `202` `PENDING`, `run_*` 패턴, `next_poll_url` 패턴.
- poll1 `RUNNING_EVIDENCE_SEARCH`, `payload == null`.
- poll2 `WAITING_FOR_APPROVAL`, `payload != null`.
- approve `200`, `brief_*` 패턴.
- Elastic: `growth_briefs` 1건 + `calendar_events` N건, 링크 일치 (`calendar_events.growth_brief_id == brief_id`, `experiment_id`가 승인 실험과 일치).
- 중복 approve → `409`.

범위 밖 (Java e2e 아님): 실 Gemini, 실 Phoenix/Arize, 실 ADK 추론.

---

## 11. 미해결 항목

- 인덱스를 부트스트랩이 생성할지, 사전 생성된 것을 사용할지 (사용자 확인 대기).
- `team_notes` 인덱스 여부 (계약 03 open decision, MVP 범위 밖).
- 승인 정정 시 `supersedes_growth_brief_id` (v0.2, MVP 범위 밖).
</content>
</invoke>
