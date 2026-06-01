# LaunchPilot Architecture Diagrams

Status: Draft v0.1  
Scope: C4 context/container/component views and main user scenario sequence  
Last updated: 2026-06-01

## 1. System Context

This C1 view shows LaunchPilot as an AI agent workroom platform used by content and growth managers. The system coordinates Gemini reasoning, Elastic evidence retrieval, and Phoenix/Arize observability behind a single product boundary.

```mermaid
graph TB
  classDef person fill:#08427b,stroke:#052e56,color:#ffffff,stroke-width:2px;
  classDef internal fill:#1168bd,stroke:#0b4884,color:#ffffff,stroke-width:2px;
  classDef external fill:#4b5563,stroke:#374151,color:#ffffff,stroke-width:2px;

  User(["콘텐츠 / 성장 매니저<br/>(Person)<br/><br/>크리에이터 팀, 기획사 담당자.<br/>SNS CSV 데이터를 업로드하고,<br/>에이전트의 실험안을 검토/승인함"]):::person

  subgraph LaunchPilot_Boundary ["LaunchPilot 시스템 경계"]
    LP["LaunchPilot 시스템<br/>(Software System)<br/><br/>비동기 오케스트레이션 파이프라인 기반의<br/>AI 에이전트 워룸 플랫폼.<br/>시그널 탐지, 인과 가설 수립, 실험안 설계의<br/>워크플로우를 제어하고 도구 사용을 중개함"]:::internal
  end

  Gemini["Google Gemini API<br/>(External System - LLM Engine)<br/><br/>시스템의 두뇌 역할을 하는 외부 파운데이션 모델.<br/>다차원 맥락 이해, 추론,<br/>도구 호출 결정을 수행함"]:::external

  Elastic["Elastic Cloud Serverless<br/>(External System - Single Data Store)<br/><br/>시스템의 유일한 데이터 저장소이자 L3 지식 엔진.<br/>앱 메타데이터, SNS 로그, 상태 로그를 통합 저장하고<br/>에이전트에게 하이브리드 근거 검색을 제공함"]:::external

  Arize["Arize AI / Phoenix Cloud<br/>(External System - Meta Memory)<br/><br/>L4 메타 기억 저장소.<br/>에이전트 실행 이력을 실시간 계측하고,<br/>능동적 자가 성찰용 피드백 데이터를 제공함"]:::external

  User -- "1. SNS 지표 CSV 데이터 업로드 및 분석 요청" --> LP
  LP -- "2. CSV 파싱 데이터 실시간 인덱싱 및 상태 로그 적재" --> Elastic
  LP -- "3. 프롬프트 및 컨텍스트 전달 / 추론 요청" --> Gemini
  Gemini -- "4. 구조화된 분석 결과 반환 및 도구 호출 지시" --> LP
  LP -- "5. 에이전트 분석에 필요한 다차원 근거 검색 (Elasticsearch MCP)" --> Elastic
  LP -- "6. 과거 실패 평가 지표 조회 (Phoenix MCP)" --> Arize
  LP -. "7. 에이전트 실행 Trace 데이터 실시간 송신 (OTel / OpenInference)" .-> Arize
  LP -- "8. 분석 결과 시각화 및 실험 제안" --> User
  User -- "9. 최종 콘텐츠 실험 계획 승인" --> LP
  LP -- "10. 최종 확정된 불변 캘린더/브리프 산출물 저장" --> Elastic
```

## 2. Container View

This C2 view shows the three deployable containers owned by LaunchPilot: Next.js frontend, Java backend, and Python agent service.

```mermaid
graph TB
  classDef person fill:#08427b,stroke:#052e56,color:#ffffff,stroke-width:2px;
  classDef container fill:#1168bd,stroke:#0b4884,color:#ffffff,stroke-width:2px;
  classDef external fill:#4b5563,stroke:#374151,color:#ffffff,stroke-width:2px;

  subgraph LaunchPilot_System ["LaunchPilot 내부 시스템 경계 (Containers We Deploy)"]
    FE["Frontend Container<br/>(React / Next.js)<br/><br/>War Room UI 제공,<br/>CSV 파일 업로드 인터페이스,<br/>인앱 캘린더/브리프 뷰 렌더링"]:::container

    BE["Business Backend<br/>(Java 21 / Spring Boot)<br/><br/>RDB 배제 / 순수 게이트웨이화.<br/>CSV 스트리밍 파싱 및<br/>Elastic 직접 즉시 인덱싱 담당"]:::container

    AG["Agent Service<br/>(Python / FastAPI / Google ADK)<br/><br/>에이전트 오케스트레이션 엔진.<br/>컨텍스트 구성, 외부 Gemini API 중개,<br/>Tool Calling 상태 머신 제어 및 JSON 파싱 전담"]:::container
  end

  User(["콘텐츠 / 성장 매니저<br/>(Person)"]):::person

  Gemini["Google Gemini API<br/>(External Container - LLM Infrastructure)<br/><br/>Agent Service로부터 컨텍스트를 받아<br/>추론 및 도구 호출 결정을 내림"]:::external

  Elastic["Elastic Cloud Serverless<br/>(External Container - Single Data Store)<br/><br/>통합 데이터 저장소 및 지식 엔진.<br/>마스터 메타, 시계열 로그, 상태 로그,<br/>캘린더 일정 등을 통합 수록하는 유일 DB"]:::external

  Arize["Arize AI / Phoenix Cloud<br/>(External Container - Meta Memory)<br/><br/>L4 메타 기억 저장소.<br/>에이전트 런타임 실행 이력 계측 및<br/>능동적 자가 성찰용 피드백 데이터 제공"]:::external

  User -->|1. UI 조작 및 CSV 파일 선택| FE
  FE -->|2. CSV 파일 전송 및 API 요청 Multipart Form| BE
  BE ==>|3. CSV 파싱 데이터 직접 실시간 인덱싱 refresh=true| Elastic

  BE -->|4. 에이전트 분석 실행 비동기 트리거 HTTP JSON| AG

  AG -- "5.1 조립된 프롬프트 및 컨텍스트 전달 / 추론 요청 HTTPS" --> Gemini
  Gemini -- "5.2 구조화된 추론 결과 반환 및 도구 호출 지시" --> AG

  AG ==>|6. Elasticsearch MCP 검색 도구 호출 및 근거 지식 수집| Elastic
  AG -->|7.1 과거 실패 패턴 및 평가 지표 조회 Phoenix MCP| Arize
  AG -.->|7.2 에이전트 실행 트레이스 실시간 송신 OTel / OpenInference| Arize

  AG -->|8. Gemini 결과 기반 최종 구조화 JSON 결과 전달| BE
  BE -->|9. 분석 상태 및 완료 결과 전송| FE
  FE -->|10. 워룸 화면에 시나리오 시각화| User

  User -->|11. 실험안 승인| FE
  FE -->|12. 승인 액션 요청 HTTP JSON| BE
  BE ==>|13. 최종 확정된 불변 캘린더 및 브리프 데이터 직접 적재| Elastic
```

## 3. Main User Scenario Sequence

This sequence highlights the stateless frontend rule: candidate experiment plans live in frontend memory until human approval. Only approved artifacts are persisted to Elastic.

```mermaid
sequenceDiagram
    autonumber
    actor User as 콘텐츠/성장 매니저
    participant FE as Frontend Container<br/>React / Next.js UI State
    participant BE as Business Backend<br/>Java 21 / Spring Boot
    participant AG as Agent Service<br/>Python / Google ADK
    participant Elastic as Elastic Cloud Serverless<br/>L3 Evidence Engine
    participant Arize as Arize AI / Phoenix<br/>L4 Observability

    Note over User, Arize: PHASE 1: 분석 요청 및 에이전트 추론 루프
    User->>FE: "What should we test next week?" 버튼 클릭
    FE->>BE: 에이전트 실행 API 요청 (POST /api/agent/run)
    BE->>AG: 내부 에이전트 실행 요청 (POST /internal/agent/runs)

    rect rgb(235, 245, 255)
        Note over AG, Arize: L4 메타 성찰 단계
        AG->>Arize: Phoenix MCP 도구 호출 (get_traces / get_evaluations)
        Arize-->>AG: 과거 낮은 평가 점수의 프롬프트/컨텍스트 패턴 반환
        AG->>AG: 실패 패턴을 반영해 추론 로직 보정
    end

    rect rgb(255, 248, 220)
        Note over AG, Elastic: L3 지식 검색 단계
        AG->>Elastic: Elasticsearch MCP 기반 Evidence wrapper 호출<br/>(search_content_posts, query_metric_baseline, search_team_notes)
        Note over Elastic: ES-QL 기반 baseline 계산 및 하이브리드 검색 수행
        Elastic-->>AG: EvidenceRef[] 구조의 근거 데이터셋 반환
    end

    AG->>AG: Gemini 기반 다단계 추론<br/>시그널 추출 -> 인과 가설 수립 -> 실험안 설계

    rect rgb(230, 245, 230)
        Note over AG, Arize: L4 실시간 트레이싱 계측
        AG->>Arize: LLM 호출, 도구 호출, Reviewer Gate 결과를 OTLP/OpenInference로 전송
    end

    AG-->>BE: 최종 구조화 결과 반환 (AgentResultPayload)
    BE-->>FE: polling 응답으로 WAITING_FOR_APPROVAL payload 전달
    Note over FE: 승인 전 후보 실험안은 React State에만 보관한다.

    Note over User, Arize: PHASE 2: 인간 피드백 반영 및 불변 데이터 적재
    User->>FE: 실험안 카드 검토, 선택, 문구 수정
    User->>FE: Approve Experiments 클릭
    FE->>BE: 승인 요청 (POST /api/agent/actions/{agent_run_id}/approve)

    rect rgb(255, 240, 245)
        Note over BE, Elastic: Append-only insert
        BE->>Elastic: growth_briefs 1건 및 calendar_events N건 bulk index
    end

    Note over FE: 승인 직후 캘린더 화면은 React State 전달로 즉시 렌더링할 수 있다.

    Note over User, Arize: PHASE 3: 새 세션에서 과거 맥락 복원
    User->>FE: 이전 분석 이어서 이야기하기 선택
    FE->>BE: 새 분석 세션 요청 (parent_brief_id 포함)
    BE->>Elastic: growth_briefs에서 승인 스냅숏 조회
    Elastic-->>BE: 과거 핵심 요약, 시그널, 가설, 실험안 반환
    BE->>AG: Google ADK 실행 인자로 과거 스냅숏 주입
    AG->>AG: 신규 세션에서 비즈니스 연속성 복원
    AG-->>FE: 이어진 워룸 화면 활성화
```

## 4. Agent Service Component View

This C3 view describes the Python Agent Service internals.

```mermaid
graph TB
  classDef component fill:#85bbf0,stroke:#1168bd,color:#000000,stroke-width:2px;
  classDef external fill:#4b5563,stroke:#374151,color:#ffffff,stroke-width:2px;
  classDef state fill:#a7f3d0,stroke:#059669,color:#000000,stroke-width:2px;
  classDef obs fill:#34d399,stroke:#059669,color:#000000,stroke-width:2px;

  BE["Business Backend<br/>(Java / Spring Boot)"]:::external
  Gemini["Google Gemini API<br/>(External LLM Infrastructure)"]:::external
  Elastic["Elastic Cloud Serverless<br/>(L3 장기 기억 / DB)"]:::external
  Arize["Arize AI / Phoenix Cloud<br/>(L4 메타 기억 / Observability)"]:::external

  subgraph Python_Agent_Container ["Python Agent Service Container Boundary (C3 Level)"]
    Ctrl["Agent API Controller<br/>(FastAPI / Routing)<br/><br/>Java의 분석/복원 비동기 요청 접수 및<br/>즉시 202 Accepted 반환 담당"]:::component
    Orch["Central Orchestrator<br/>(State Machine Engine)<br/><br/>Background task에서 워커 제어,<br/>품질 실패 시 백트래킹 루프 관장"]:::component
    State["Shared Context Object<br/>(Pydantic State Store)<br/><br/>L1/L2 단기 기억 격리소.<br/>Signals -> Hypotheses -> Experiments<br/>단계별 JSON 데이터 축적"]:::state
    WorkerA["Data Analyst Worker<br/>(Sub-Agent / 정량 분석)"]:::component
    WorkerB["Data Strategist Worker<br/>(Sub-Agent / 인과 가설)"]:::component
    WorkerC["Data Writer Worker<br/>(Sub-Agent / 기획 문서화)"]:::component
    Gate["Reviewer Gate Component<br/>(Validator / Guardrail)"]:::component
    MCP["Elastic MCP Client<br/>(Evidence Retrieval Tool)<br/><br/>Elasticsearch MCP 기반<br/>검색 및 ES-QL 집계 wrapper"]:::component
    ArizeMCP["Phoenix MCP Client<br/>(Self-Introspection Tool)<br/><br/>과거 실패 Trace 및 평가 결과 조회"]:::obs
    Tracer["Tracer Module<br/>(OpenTelemetry / OpenInference)<br/><br/>LLM I/O 및 MCP 실행 이력 실시간 계측"]:::component
  end

  BE -->|1. 비동기 분석 또는 복원 요청 트리거| Ctrl
  Ctrl -->|2. Job ID 접수 후 Background task 구동| Orch
  Orch -.->|3. 초기 세션 및 parent_brief_id 기반 컨텍스트 적재| State

  Orch -->|4. 정량 시그널 탐지 명령| WorkerA
  WorkerA -->|4.1. 시계열 로그 검색 도구 호출| MCP
  MCP -->|4.2. ES-QL 기반 통계 집계 쿼리| Elastic
  WorkerA ==>|4.3. 정량 시그널 추출/추론 요청 HTTPS| Gemini
  Gemini ==>|4.4. 구조화된 분석 결과 반환| WorkerA
  WorkerA -.->|4.5. 탐지된 정량 시그널 적재| State

  Orch -->|5. 인과 가설 및 실험 설계 명령| WorkerB
  State -.->|5.1. 누적된 시그널 데이터 참조| WorkerB
  WorkerB -->|5.2. 팀 메모 하이브리드 검색 도구 호출| MCP
  MCP -->|5.3. 텍스트 시맨틱 검색| Elastic
  WorkerB ==>|5.4. 가설 및 실험안 설계 추론 요청 HTTPS| Gemini
  Gemini ==>|5.5. 가설/실험 구조화 데이터 반환| WorkerB
  WorkerB -.->|5.6. 가설 및 실험 데이터셋 적재| State

  Orch -->|6. 품질 가드레일 및 안전성 검증 위임| Gate
  State -.->|6.1. 완성된 결과물 스키마 전수 검사| Gate
  Gate -->|6.2. Phoenix MCP 성찰 도구 호출| ArizeMCP
  ArizeMCP -->|6.3. 과거 실패 평가 기록 조회| Arize
  Gate ==>|6.4. 실패 패턴 복기 및 무결성 자체 검증 요청 HTTPS| Gemini
  Gemini ==>|6.5. 검증 Pass/Fail 판단 및 교정 텍스트 반환| Gate

  Gate -->|6.6. Fail: 스키마 무결성 결여 시 피드백 전송| Orch
  Orch -->|6.7. 수정 요구사항 포함 재실행 명령| WorkerB

  Gate -->|7. Pass: 검증 완료 관문 통과| Orch
  Orch -->|7.1. 최종 브리프 생성 명령| WorkerC
  WorkerC ==>|7.2. 최종 마크다운 및 브리프 생성 요청 HTTPS| Gemini
  Gemini ==>|7.3. 정제된 마크다운 및 브리프 데이터 반환| WorkerC
  WorkerC -.->|7.4. 최종 완료본 브리프 스냅숏 적재| State

  Orch -->|8. 해당 Job ID 상태를 WAITING_FOR_APPROVAL로 업데이트| Ctrl
  Ctrl -->|9. 최종 AgentResultPayload 반환| BE

  WorkerA -.->|OTel / OpenInference 계측| Tracer
  WorkerB -.->|OTel / OpenInference 계측| Tracer
  WorkerC -.->|OTel / OpenInference 계측| Tracer
  Gate -.->|OTel / OpenInference 계측| Tracer
  MCP -.->|OTel / OpenInference 계측| Tracer
  ArizeMCP -.->|OTel / OpenInference 계측| Tracer
  Tracer -->|원격 추적 데이터 전송 OTLP| Arize
```

## 5. Java Backend Component View

This C3 view describes the Java Spring Boot backend internals.

```mermaid
graph LR
  classDef ext fill:#4b5563,stroke:#374151,color:#ffffff,stroke-width:1px;
  classDef core fill:#1168bd,stroke:#0b4884,color:#ffffff,stroke-width:2px;
  classDef service fill:#85bbf0,stroke:#1168bd,color:#000000,stroke-width:1px;
  classDef client fill:#f59e0b,stroke:#d97706,color:#ffffff,stroke-width:1px;

  NextJS["Frontend App<br/>(Next.js)"]:::ext
  Elastic[("Elastic Cloud Serverless<br/>(Single Data Store)")]:::ext
  PyAgent["Python Agent Container<br/>(Evaluator-Optimizer Pipeline)"]:::ext

  subgraph Java_Backend_Container ["Java Spring Boot Backend Container Boundary (C3 Level)"]
    subgraph API_Tier ["Tier 1: Web API Layer"]
      Ctrl_Import["ImportController<br/>(Seed / CSV Ingestion)"]:::core
      Ctrl_Agent["AgentController<br/>(Task Trigger / Polling)"]:::core
      Ctrl_Biz["BusinessController<br/>(Calendar / Growth Brief)"]:::core
    end

    subgraph Service_Tier ["Tier 2: Business Service Layer"]
      ImpService["ImportService<br/><br/>데이터 수집/파싱 제어 및<br/>벌크 인덱싱 파이프라인 지휘"]:::service
      Parser["CsvStreamingParser<br/><br/>OOM 방지용 chunk-based iterator loader"]:::service
      JobMgr["AgentAsyncJobManager<br/><br/>Tomcat 스레드 고갈 방지용<br/>TaskExecutor 기반 비동기 잡 스케줄러"]:::service
      BizService["BusinessDataService<br/><br/>유저 승인에 따른 불변 데이터 빌드 및<br/>인앱 비즈니스 로직 담당"]:::service
    end

    subgraph Client_Tier ["Tier 3: Infrastructure Client Layer"]
      ES_Client["Elasticsearch Client<br/><br/>고속 REST 클라이언트.<br/>refresh 옵션 기반 실시간성 확보 및<br/>다차원 벌크 도큐먼트 upsert 담당"]:::client
    end
  end

  NextJS -->|1. CSV 업로드 / Seed 수집 요청| Ctrl_Import
  Ctrl_Import --> ImpService
  ImpService -->|1.1. Iterator 기반 한 줄씩 읽기 스트리밍 호출| Parser
  Parser -.->|1.2. 힙 메모리 최소화 상태로 청크 데이터 전달| ImpService
  ImpService -->|1.3. 실시간성 강제 옵션 기반 벌크 인덱싱 요청| ES_Client

  NextJS -->|2. 분석 요청 트리거 / 상태 polling| Ctrl_Agent
  Ctrl_Agent --> JobMgr
  JobMgr -->|2.1. 웹 스레드 즉시 해제 / 202 Accepted 반환| Ctrl_Agent
  JobMgr -->|2.2. 독립 스레드 풀에서 비동기 HTTP 요청| PyAgent

  NextJS -->|3. 가설 실험안 최종 승인 / 인앱 브리프 조회| Ctrl_Biz
  Ctrl_Biz --> BizService
  BizService -->|3.1. 승인 완료된 불변 캘린더/브리프 산출물 빌드| ES_Client

  ES_Client <==>|Elastic High-Level REST API 통신 및 refresh 쿼리 적용| Elastic
```

## 6. Contract Map

The architecture above is enforced by the contract set under `contracts/`.

| Architecture Boundary | Contract Folder |
| --- | --- |
| Frontend <-> Java Backend | `contracts/01-frontend-java` |
| Java Backend <-> Python Agent | `contracts/02-java-python-agent` |
| Java Backend <-> Elastic documents | `contracts/03-java-elastic` |
| Python Agent <-> Elasticsearch MCP | `contracts/04-agent-elastic-mcp` |
| Agent structured output and Reviewer Gate | `contracts/05-agent-output` |
| OpenInference / Phoenix observability | `contracts/06-observability` |
