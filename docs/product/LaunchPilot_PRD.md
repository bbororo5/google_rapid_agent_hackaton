# LaunchPilot PRD
## Growth Signal-to-Experiment Agent (멀티 에이전트 리뉴얼판)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v2.0 (conversation-first stream contract) |
| 작성일 | 2026-06-02 |
| 제출 목적 | Google Cloud Rapid Agent Hackathon 신규 프로젝트 개발 문서 |
| Partner Track | Elastic |
| AI / Agent | Gemini + Google ADK (Agent Development Kit) 멀티 에이전트 |
| 관측성 | Arize AI / Phoenix Cloud + OpenInference / OpenTelemetry |
| 핵심 제품 루프 | Signal → Hypothesis → Experiment → Approval → Brief → Continuity |
| 제출 원칙 | 새 repo, 새 코드베이스, 새 demo dataset. 기존 운영 서비스 수정/확장 아님 |

> 본 문서는 기존 v0.1 PRD를 `contracts/`, `scenarios/`, `docs/architecture/launchpilot-c4.md` 설계에 맞춰 전면 리뉴얼한 버전이다.
> 가장 큰 설계 결정은 다음 여섯 가지다.
> 1. 단일 LangChain류 에이전트 → **Google ADK 기반 4개 워커 멀티 에이전트** 파이프라인.
> 2. Google Cloud Agent Builder 사용 → **Google ADK 직접 오케스트레이션** + Elasticsearch MCP Server.
> 3. 별도 App DB(Postgres/SQLite) → **Elastic Cloud Serverless 단일 데이터 저장소**, Java 백엔드는 순수 게이트웨이.
> 4. 관측성 부재 → **Arize/Phoenix L4 메타 기억** 및 OpenInference 트레이싱 추가.
> 5. 버튼 중심 process flow가 아니라 **자유 대화 main stream**을 제품의 기본 표면으로 둔다.
> 6. 프론트 계약은 단일 송신 `message.send`와 단일 수신 `StreamMessage.blocks[]`만 노출한다.

---

## 1. Executive Summary

### 1.1 제품명

**LaunchPilot**

### 1.2 한 줄 설명

LaunchPilot은 크리에이터 팀의 SNS 성과 CSV를 해석해, 중요한 성장 신호를 찾고, 원인 가설을 세우며, 다음 주 검증 가능한 콘텐츠 실험안으로 바꿔주는 AI 멀티 에이전트 워룸이다.

### 1.3 핵심 사용자

1차 타겟은 다음 네 그룹이다.

| 사용자 | 핵심 상황 |
|---|---|
| 소규모 기획사 | 여러 아티스트/크리에이터의 콘텐츠 성과를 관리하고 다음 콘텐츠 전략을 정해야 함 |
| 인플루언서 매니저 | 담당 크리에이터의 주간 성과를 해석하고 클라이언트/대표에게 보고해야 함 |
| 1~5인 크리에이터 팀 | 여러 SNS 채널 데이터를 엑셀·노션·수동 캡처로 관리하며 다음 콘텐츠를 감으로 정함 |
| 브랜드 SNS 담당자 | 캠페인별 ROI와 다음 A/B 테스트 방향을 설명해야 함 |

2차 타겟은 최근 60일 내 콘텐츠 30개 이상이 쌓인 성장 중인 개인 크리에이터다.

### 1.4 핵심 문제

사용자는 SNS 데이터를 볼 수는 있지만, 다음 질문에 명확히 답하지 못한다.

- 이번 주 데이터에서 진짜 중요한 변화는 무엇인가?
- 어떤 콘텐츠가 성장 변화와 가장 강하게 연결되어 있는가?
- 이 변화는 우연인가, 반복 가능한 신호인가?
- 다음 주에는 무엇을 A/B 테스트해야 하는가?
- 팀이나 클라이언트에게 이 결과를 어떻게 설명해야 하는가?

### 1.5 핵심 가치

LaunchPilot은 단순 대시보드나 주간 리포트 생성기가 아니다. 사용자가 직접 차트를 읽고 회의에서 해석해야 했던 과정을 다음 흐름으로 압축한다.

> **Signal → Hypothesis → Experiment → Approval → Brief → Continuity**

제품의 최종 결과물은 "지난주 요약"이 아니라 **사람이 승인한, 캘린더에 반영되는 다음 주 실행 가능한 콘텐츠 실험안**이다. 그리고 그 승인 결과는 다음 분석 세션의 출발점이 되어 캠페인 학습 루프를 형성한다.

### 1.6 해커톤 제출 전략

- **Track:** Elastic
- **핵심 차별점:** Elastic을 단일 evidence engine 겸 유일 데이터 저장소로 사용해 구조화 SNS 성과와 비구조화 팀 메모/과거 브리프를 함께 검색한다.
- **에이전트성 증명:** 단일 챗봇이 아니라 **역할이 분리된 4개의 ADK 워커**가 검색 → 신호 → 가설 → 실험 설계를 분담하고, **Reviewer Gate**가 결과를 검증·백트래킹하며, **Phoenix MCP**로 과거 실패를 성찰한다.
- **관측성:** 모든 LLM 호출과 도구 호출을 OpenInference 스팬으로 계측해 에이전트의 추론 경로를 심사위원이 추적할 수 있다.
- **데모 전략:** 실제 SNS API 연동은 제외. CSV import로 안정적인 3분 데모를 구성하고, 모델 지연 시 deterministic fallback을 제공한다.

---

## 2. Problem Definition

### 2.1 사용자의 현재 업무 방식

소규모 크리에이터 팀과 매니저는 보통 다음 방식으로 일한다.

1. Instagram, TikTok, YouTube, X 등 여러 앱에서 성과 수치를 확인한다.
2. 조회수, 좋아요, 댓글, 저장, 팔로워 변화를 엑셀·노션·스프레드시트로 옮긴다.
3. 잘 된 콘텐츠와 안 된 콘텐츠를 사람이 눈으로 비교한다.
4. 회의에서 "왜 잘 됐는지"를 감으로 해석한다.
5. 다음 주 콘텐츠 아이디어를 브레인스토밍한다.
6. 클라이언트/대표에게 보고서를 만든다.

이 과정의 병목은 데이터 수집만이 아니다. 더 큰 병목은 **데이터 해석과 다음 실험 설계**다.

### 2.2 기존 SNS 분석 도구의 한계

Later, Metricool, Sprout Social류의 도구는 성과를 보여주는 데 강하다. 하지만 사용자의 실무 질문은 다음에 가깝다.

- "이 숫자에서 뭘 봐야 하는가?"
- "왜 이 콘텐츠가 튄 것으로 보이는가?"
- "다음 주에 어떤 실험을 해야 하는가?"
- "보고서에 어떤 문장으로 설명해야 하는가?"

기존 대시보드는 차트를 제공하지만, **차트에서 실험안으로 넘어가는 사고 과정**을 자동화하지 않는다. LaunchPilot은 그 사고 과정 자체를 여러 전문 에이전트의 협업으로 자동화한다.

### 2.3 LaunchPilot이 해결하는 Pain Point

| Pain Point | LaunchPilot의 해결 방식 | 담당 |
|---|---|---|
| 숫자는 많은데 중요한 변화가 무엇인지 모름 | baseline 대비 튄 성과를 자동 탐지해 Signal Card로 요약 | Data Analyst Worker |
| 콘텐츠와 성장 변화의 관계 해석이 어려움 | Elastic에서 콘텐츠/캠페인/캘린더/팀 메모를 함께 검색해 근거화 | Elastic MCP Wrapper |
| 원인 추정이 감에 의존함 | evidence 기반 가설, confidence·caveat 포함 생성 | Data Strategist Worker |
| 다음 콘텐츠 아이디어가 감으로 나옴 | 검증 가능한 Experiment Plan 생성 | Data Writer Worker |
| AI 결과를 못 믿음 | 스키마·근거 무결성 검증 후에만 사용자에게 노출 | Reviewer Gate |
| 같은 실수를 반복함 | 과거 낮은 평가 트레이스를 성찰해 추론 보정 | Phoenix MCP |
| 보고서 작성 시간이 오래 걸림 | 1페이지 Growth Brief 자동 생성 | Data Writer Worker |
| 지난 의사결정과 단절됨 | parent_brief_id로 캠페인 학습 루프 복원 | 복원 플로우 |

### 2.4 해결하지 않는 문제 (MVP 제외)

- Instagram/TikTok/X 실시간 공식 API 연동
- 자동 게시 또는 자율 업로드
- 광고 예산 최적화
- 고급 예측 모델링
- 멀티 워크스페이스 권한 관리
- 결제/과금/프로덕션 SaaS 운영 기능

---

## 3. Target Users & Jobs To Be Done

### 3.1 1차 타겟

#### A. 소규모 기획사
- 상황: 2~10명의 아티스트/크리에이터 캠페인을 동시에 운영한다.
- 문제: 매주 어떤 콘텐츠가 반응을 만들었는지 정리하고 다음 방향을 잡아야 한다.
- JTBD: "캠페인 회의 전에, 어떤 콘텐츠 포맷을 더 테스트해야 하는지 근거와 함께 정리하고 싶다."

#### B. 인플루언서 매니저
- 상황: 담당 크리에이터의 채널 성장을 주간 단위로 보고한다.
- 문제: 단순 수치 요약은 가능하지만, 왜 성장했는지와 다음 액션을 설명하기 어렵다.
- JTBD: "주간 성과 데이터를 보고, 클라이언트에게 설명 가능한 성장 신호와 다음 실험안을 만들고 싶다."

#### C. 1~5인 크리에이터 팀
- 상황: 기획자, 편집자, 출연자가 소규모로 운영한다.
- 문제: SNS별 인사이트를 보지만 다음 주 계획은 감으로 정한다.
- JTBD: "지난 콘텐츠 성과를 바탕으로 다음 주에 무엇을 실험할지 빠르게 결정하고 싶다."

### 3.2 2차 타겟

#### 성장 중인 개인 크리에이터
- 조건: 최근 60일 내 콘텐츠 30개 이상, 주 3회 이상 업로드.
- 문제: 스스로 데이터를 해석하기 어렵고, 어떤 포맷을 반복해야 할지 모른다.
- JTBD: "내 계정에서 반복되는 성장 신호를 찾아 다음 콘텐츠 아이디어로 바꾸고 싶다."

---

## 4. Product Positioning

### 4.1 이 제품이 아닌 것
- 단순 SNS 대시보드
- 단순 AI 챗봇
- 단순 주간 보고서 생성기
- 단순 캡션 생성기
- 자동 게시 도구
- API 연동 중심 데이터 파이프라인 도구

### 4.2 이 제품인 것

LaunchPilot은 **멀티 에이전트 Signal-to-Experiment 워룸**이다.

사용자가 데이터를 읽는 대신, 역할이 분리된 에이전트들이 협업한다.

1. **Data Analyst Worker** 가 데이터를 검색하고 정량 신호를 찾는다.
2. **Data Strategist Worker** 가 신호의 원인 후보를 가설화한다.
3. **Data Writer Worker** 가 다음 주 실험안과 브리프를 설계한다.
4. **Reviewer Gate** 가 스키마와 근거 무결성을 검증하고, 실패 시 되돌린다.
5. 사용자가 검토·수정·승인하면, 승인본만 Elastic에 불변 저장된다.

### 4.3 경쟁 도구와의 차별점

| 구분 | 일반 SNS 분석 도구 | LaunchPilot |
|---|---|---|
| 중심 가치 | 성과 시각화 | 데이터 해석과 실험 설계 |
| 사용자 역할 | 차트를 보고 직접 판단 | 에이전트가 신호·가설·실험을 제안, 사람은 승인 |
| AI 구조 | 단일 요약/Q&A | 역할 분리 4-워커 + Reviewer Gate 백트래킹 |
| 결과물 | 대시보드, 리포트 | 승인된 실험 계획, 캘린더, Growth Brief |
| 근거 제시 | 제한적 | Evidence Drawer + 도구 호출 로그 |
| 신뢰성 | 검증 없음 | 결정적 검증 게이트 통과 후에만 노출 |
| 관측성 | 없음 | OpenInference 트레이스로 추론 경로 추적 |
| 연속성 | 매번 새 분석 | parent_brief_id 기반 캠페인 학습 루프 |

---

## 5. System Architecture

이 장은 v0.1에서 가장 크게 바뀐 부분이다. 상세 다이어그램은 `docs/architecture/launchpilot-c4.md` 참조.

### 5.1 배포 컨테이너 (우리가 배포하는 3개)

| 컨테이너 | 스택 | 책임 |
|---|---|---|
| Frontend | React / Next.js | War Room UI, CSV 업로드, 캘린더/브리프 뷰. **Java 공개 API만 호출한다.** |
| Business Backend | Java 21 / Spring Boot | 순수 게이트웨이. `thread_id` 생성, CSV 스트리밍 파싱, Elastic 즉시 인덱싱, 비동기 잡 관리, 승인 시 불변 적재. **RDB 미사용.** |
| Agent Service | Python / FastAPI / Google ADK | 멀티 에이전트 오케스트레이션. Gemini 호출, Elastic MCP 검색, Phoenix MCP 성찰, OpenInference 트레이싱, 후보 payload 생성. **사람 승인은 처리하지 않는다.** |

### 5.2 외부 시스템 (3개)

| 시스템 | 역할 |
|---|---|
| Google Gemini API | 시스템의 두뇌. 추론, 도구 호출 결정, 구조화 생성. |
| Elastic Cloud Serverless | **유일한 데이터 저장소이자 L3 지식 엔진.** 앱 메타, SNS 로그, 캘린더, 브리프를 통합 저장하고 하이브리드 근거 검색을 제공한다. |
| Arize AI / Phoenix Cloud | **L4 메타 기억.** 실행 이력 실시간 계측, 능동적 자가 성찰용 피드백 제공. |

### 5.3 핵심 설계 원칙

1. **단일 데이터 저장소.** Postgres/SQLite 없음. Elastic이 유일 DB. Java는 RDB 없이 Elastic에 직접 `refresh=true`로 즉시 인덱싱한다.
2. **Frontend는 stateless 경계.** 승인 전 후보 실험안은 React State에만 존재한다. 오직 승인된 산출물만 Elastic에 들어간다.
3. **Append-only 불변성.** 승인 시 `growth_briefs` 1건 + `calendar_events` N건만 bulk index. 수정/삭제 없음.
4. **대화형 WebSocket 스트리밍.** Java는 thread 단위 WebSocket을 열고, 프론트는 사용자 발화를 `message.send`로 보낸다. Java는 Agent Core 출력과 비즈니스 결과를 `StreamMessage.blocks[]`로 정규화해 sequence를 부여하고 프론트에 전달한다. WebSocket은 transport이며, 제품 계약은 단일 송신 `message.send`와 단일 수신 `StreamMessage`만 노출한다.
5. **Agent Builder 미사용.** Google ADK로 직접 오케스트레이션하고, Elasticsearch MCP Server를 LaunchPilot 도메인 wrapper로 감싸 호출한다.
6. **Glass-box 스트리밍.** Python은 raw Gemini chunk, chain-of-thought, `thoughtSignature`, raw MCP 메시지를 전송하지 않는다. 사람이 봐도 되는 정규화된 메시지 block만 스트리밍한다. **승인 게이트와 불변 저장은 Java 소유**이며 Agent Core는 대화 맥락 속 승인 의도 해석까지만 담당한다.

### 5.4 메모리 4계층

| 계층 | 저장소 | 내용 |
|---|---|---|
| L1/L2 단기 기억 | Shared Context Object (Pydantic State Store, Python 인메모리) | 한 conversation turn 동안 Signals → Hypotheses → Experiments 단계별 JSON 누적 |
| L3 장기 기억 | Elastic Cloud Serverless | SNS 로그, 콘텐츠, 캠페인, 캘린더, 팀 메모, 승인된 과거 브리프 |
| L4 메타 기억 | Arize / Phoenix Cloud | 과거 실행 트레이스, 평가 점수, 실패 패턴. Phoenix MCP로 조회 |

### 5.5 컨테이너 데이터 흐름 (요약)

```text
User → FE : 자유 대화 + 필요 시 CSV 첨부
FE   → BE : POST /api/import/csv (multipart)
BE   ⇒ ES : CSV 파싱 데이터 즉시 인덱싱 (refresh=true)
FE   ⇄ BE : WebSocket thread stream — message.send / StreamMessage
BE   ⇄ AG : Agent Core 대화/작업 컨텍스트 전달
AG   → Phoenix : 과거 실패 패턴 조회 (L4 성찰)
AG   ⇒ ES : Elastic MCP wrapper로 근거 검색 (L3)
AG   → Gemini : 신호 → 가설 → 실험 다단계 추론
AG   ⇒ BE : user-safe block 출력
BE   ⇒ FE : StreamMessage.blocks[] 스트리밍
AG   → Phoenix : LLM/도구/Gate 결과 OpenInference 송신
BE   ⇒ FE : approval block (Java가 승인 게이트 추가)
User → FE : 자유 발화 또는 버튼으로 승인 의사 표현
FE   → BE : message.send(content + optional action hint)
BE   ⇒ ES : growth_briefs 1 + calendar_events N bulk index (불변)
BE   ⇒ FE : result block (growth_brief_id + 캘린더 + persisted_at)
```

---

## 6. The Four Agents (핵심 리뉴얼)

LaunchPilot의 에이전트성은 **단일 LLM이 아니라 역할이 분리된 4개 ADK 워커 + 1개 오케스트레이터**의 협업에서 나온다. 각 워커는 좁은 책임만 갖고, 자신의 단계 산출물(draft schema)만 만든다. 최종 canonical payload는 별도 Assembler가 조립한다. (`contracts/05-agent-output` 참조)

> 워커별 "언제 어떤 도구를 호출하고 실패 시 어떻게 분기하는지"의 상세 결정 로직은 `docs/agent-tool-spec.md` 참조. 요약: 분석가 2도구 / 전략가 1도구(team_notes) / 작가·검수자 0도구 / `load_growth_brief_context`는 Orchestrator 선주입.

### 6.1 역할 분담 한눈에

| # | 에이전트 | 역할 | 입력 | 산출물(draft) | 주 사용 도구 |
|---|---|---|---|---|---|
| 1 | **Data Analyst Worker** | 정량 분석 / 신호 탐지 | 시계열·콘텐츠 로그 | `SignalDraftOutput` | `query_metric_baseline`, `search_content_posts` |
| 2 | **Data Strategist Worker** | 인과 가설 수립 | 누적 시그널 + 근거 | `HypothesisDraftOutput` | `search_team_notes`, (시그널 참조) |
| 3 | **Data Writer Worker** | 실험 설계 / 문서화 | 가설 + 캠페인 제약 | `ExperimentPlanDraftOutput`, 최종 브리프 마크다운 | (Gemini 생성 중심) |
| 4 | **Reviewer Gate** | 검증 / 가드레일 | 모든 누적 산출물 | `ValidationReport` (pass/fail + retry_instruction) | `Phoenix MCP` 성찰 |

이를 묶는 것이 **Central Orchestrator (State Machine Engine)** 이다. 오케스트레이터는 워커를 순서대로 구동하고, Reviewer Gate가 fail을 반환하면 해당 워커로 **백트래킹**시켜 재실행한다.

### 6.2 에이전트 운영 원칙 (전 워커 공통)

1. 근거 없는 결론을 내지 않는다. 모든 시그널·가설은 evidence_ref를 가진다.
2. causal claim을 피하고 correlation/evidence wording을 쓴다.
3. 모든 hypothesis는 confidence와 caveat를 포함한다.
4. 실행 action은 사용자 승인 후에만 일어난다(Python은 승인 처리 안 함).
5. 데이터가 부족하면 `insufficient_data`를 반환한다.
6. evidence_ref는 evidence 도구가 실제 반환한 ref_id만 사용한다(환각 금지).

### 6.3 Agent 1 — Data Analyst Worker (정량 분석)

- **목표:** "이번 주에 무엇을 봐야 하는가?"에 대한 정량 신호를 찾는다.
- **동작:**
  1. `query_metric_baseline` (ES|QL)로 채널·지표별 current vs baseline 집계를 계산한다. 예: TikTok save_rate 현재 0.074 vs 30일 baseline 0.026 → lift 2.8x.
  2. `search_content_posts`로 급등 구간과 같은 시간대의 고성과 포스트를 검색한다.
  3. 후보 anomaly를 ranking한다.
  4. tool 결과와 draft 텍스트를 Shared Context에 적재한다.
  5. 도구 없는 formatter 단계가 `SignalDraftOutput` (strict schema)을 방출한다.
- **산출물 규칙:** `evidence_refs`에는 `search_content_posts`, `query_metric_baseline`, `search_team_notes`, `load_growth_brief_context`가 반환한 ref_id만 들어간다.
- **상태:** `RUNNING_SIGNAL_DETECTION` → `RUNNING_EVIDENCE_SEARCH`

### 6.4 Agent 2 — Data Strategist Worker (인과 가설)

- **목표:** 정량 신호의 "왜"를 가설로 만든다.
- **동작:**
  1. Shared Context에서 누적된 시그널을 참조한다.
  2. `search_team_notes`로 팬 반응·운영 메모 등 정성 근거를 하이브리드 검색한다.
  3. Gemini로 각 신호에 대한 원인 후보 가설을 작성한다.
  4. 각 가설은 최소 1개 signal ID와 최소 1개 유효 evidence_ref를 참조한다.
  5. formatter가 `HypothesisDraftOutput`을 방출한다.
- **산출물 규칙:** 모든 가설은 `confidence`, `supporting_evidence_refs`, `caveats`(최소 1개)를 포함한다. "caused"가 아니라 "associated with / candidate driver" 표현을 강제한다.
- **상태:** `RUNNING_HYPOTHESIS_GENERATION`

### 6.5 Agent 3 — Data Writer Worker (실험 설계 / 문서화)

- **목표:** 가설을 다음 주 검증 가능한 실험안과 공유용 브리프로 바꾼다.
- **동작:**
  1. 각 가설에 대해 실험 item을 설계한다. 채널, 콘텐츠 포맷, hook, CTA, 목표 지표, 성공 기준, 일정, 제작 브리프를 포함한다.
  2. 각 item은 기존 hypothesis ID를 참조한다.
  3. 프론트가 추가 LLM 호출 없이 바로 승인할 수 있을 만큼 충분한 정보를 담는다.
  4. formatter가 `ExperimentPlanDraftOutput`을 방출한다.
  5. (Reviewer Gate Pass 이후) 최종 1페이지 Growth Brief 마크다운을 생성한다.
- **산출물 규칙:** 각 item은 `target_metric`과 `success_criteria`를 반드시 가진다. 채널은 허용 enum(`youtube/tiktok/instagram/x/unknown`)만.
- **상태:** `RUNNING_EXPERIMENT_GENERATION`

### 6.6 Agent 4 — Reviewer Gate (검증 / 백트래킹)

- **목표:** 사용자에게 노출하기 전에 무결성을 보장한다.
- **2계층 검증:**
  1. **결정적 검증(authoritative):** Python에서 Pydantic/JSON Schema + evidence_ref 집합 검사. 이 층이 최종 권한을 가진다.
  2. **Gemini 보조 비평(optional):** 설명·교정 지시 생성. 단, 결정적 실패를 뒤집을 수 없다.
- **Phoenix MCP 성찰:** 과거 낮은 평가 점수의 프롬프트/컨텍스트 패턴을 조회해 같은 실패를 반복하지 않도록 검증 기준을 보정한다.
- **이슈 코드:** `SCHEMA_INVALID`, `UNKNOWN_EVIDENCE_REF`, `UNKNOWN_SIGNAL_ID`, `UNKNOWN_HYPOTHESIS_ID`, `EMPTY_EXPERIMENT_PLAN`, `MISSING_SUCCESS_CRITERIA`, `MISSING_SCHEDULE`, `LOW_CONFIDENCE_WITHOUT_CAVEAT`, `UNSUPPORTED_CHANNEL`, `UNSAFE_OR_UNGROUNDED_CLAIM`.
- **백트래킹 규칙:**
  - fail 시 `passed=false`, `severity=blocking`, machine-readable `path` 포함, 간결한 `retry_instruction` 생성.
  - 오케스트레이터가 `retry_count`를 증가시키고 해당 워커(주로 Strategist/Writer)를 재실행한다.
  - 설정된 retry limit 초과 시 Python이 Java에 `FAILED`를 반환한다.
- **상태:** `current_stage = VALIDATING`. Pass 시 Final Payload Assembler가 `AgentResultPayload`를 조립하고 `WAITING_FOR_APPROVAL`로 전이.

### 6.7 Central Orchestrator (State Machine Engine)

워커가 아니라 이들을 제어하는 상태 머신이다.

- Java의 비동기 요청을 받아 Background task에서 워커를 순차 구동한다.
- Reviewer Gate의 pass/fail에 따라 진행 또는 백트래킹을 결정한다.
- 초기 세션에서 `parent_brief_id`가 있으면 `load_growth_brief_context`로 과거 스냅숏을 주입한다.
- 모든 단계를 Tracer 모듈을 통해 OpenInference로 계측한다.

### 6.8 Agent activity projection

```text
PENDING
  → RUNNING_SIGNAL_DETECTION        (Data Analyst)
  → RUNNING_EVIDENCE_SEARCH         (Elastic MCP wrapper)
  → RUNNING_HYPOTHESIS_GENERATION   (Data Strategist)
  → RUNNING_EXPERIMENT_GENERATION   (Data Writer)
  → [VALIDATING]                    (Reviewer Gate)
        ├─ Fail → 백트래킹 → 해당 워커 재실행 (retry_count++)
        └─ Pass → Final Payload Assembler
  → WAITING_FOR_APPROVAL            (Python 터미널 상태)
  → (Java) SUCCESS                  (사용자 승인 후 Java 라이프사이클)

Error:
  → FAILED     (retry limit 초과 또는 복구 불가 인프라 오류)
  → CANCELLED  (후보 생성 완료 전 사용자/운영자 취소)
```

> `WAITING_FOR_APPROVAL`은 Python의 성공 터미널 상태다. `SUCCESS`는 Java 승인 라이프사이클 전용이며 Python v0.1은 방출하지 않는다.
>
> 프론트는 이 내부 상태를 화면 상태 머신으로 복제하지 않는다. 사용자에게 보이는 진행·승인·오류는 `StreamMessage.blocks[]`의 `activity`, `approval`, `result`, `error`로 표현한다.

---

## 7. Evidence Layer (Elasticsearch MCP + Wrapper)

상세는 `contracts/04-agent-elastic-mcp` 참조.

### 7.1 두 개의 도구 계층

| 계층 | 소유 | 도구 | 용도 |
|---|---|---|---|
| Elasticsearch MCP Server | Elastic | `list_indices`, `get_mappings`, `search`, `esql`, `get_shards` | 범용 ES 접근 |
| LaunchPilot Evidence Wrapper | Python Agent | `search_content_posts`, `query_metric_baseline`, `search_team_notes`, `load_growth_brief_context` | 도메인 안전 도구 |

ADK 워커는 **raw MCP 도구를 직접 호출하지 않고** wrapper 도구만 호출한다. wrapper가 안전한 DSL/ES|QL 구성, 인덱스 제한, 결과 정규화를 책임진다.

### 7.2 Wrapper 도구

| Wrapper | 하위 MCP | 인덱스 | 목적 |
|---|---|---|---|
| `search_content_posts` | `search` | `content_posts` | 근거용 고성과 포스트/지표 행 검색 |
| `query_metric_baseline` | `esql` | `content_posts` | current/baseline 지표 집계 (metric-agnostic) |
| `search_team_notes` | `search` | `team_notes` | 정성 팀 메모 검색 (v0.1 optional) |
| `load_growth_brief_context` | `search` | `growth_briefs` | `parent_brief_id` 복원용 과거 승인 브리프 로드 |

`query_metric_baseline`은 save_rate, engagement_rate, views, follower_count 등 임의 수치 지표를 처리하도록 metric-agnostic하게 설계되었다.

### 7.3 EvidenceRef (정규화 단위)

```json
{
  "ref_id": "post_014",
  "ref_type": "content_post",
  "source_index": "content_posts",
  "title": "Practice room BTS clip",
  "summary": "TikTok BTS clip with save_rate 0.074, 2.8x above baseline.",
  "timestamp": "2026-05-27T20:00:00+09:00",
  "score": 0.92,
  "metrics": { "save_rate": 0.074, "views": 120000 }
}
```

허용 `ref_type`: `content_post`, `metric_aggregate`, `team_note`, `growth_brief`.

`evidence_refs[].ref_id`만 최종 payload의 `signals[].evidence_refs`, `hypotheses[].supporting_evidence_refs`, `growth_briefs.source_evidence_refs`로 복사될 수 있다.

### 7.4 근거 무결성 규칙

- 최종 payload에 raw ES DSL, ES|QL 문자열, 자격증명, MCP 전송 메시지를 절대 포함하지 않는다.
- evidence 도구가 반환하지 않은 ref_id는 사용 금지(Reviewer Gate가 `UNKNOWN_EVIDENCE_REF`로 차단).
- `team_notes` 미가용 시 wrapper는 환각 대신 `ok:false, code:INDEX_UNAVAILABLE`을 반환한다.

---

## 8. Observability (L4 Phoenix / Arize)

상세는 `contracts/06-observability` 참조.

### 8.1 역할

- **실시간 계측:** 모든 LLM 호출, MCP 도구 호출, Reviewer Gate 결과를 OpenTelemetry / OpenInference 스팬으로 Arize/Phoenix에 송신한다.
- **자가 성찰(L4):** Reviewer Gate가 Phoenix MCP(`get_traces` / `get_evaluations`)로 과거 낮은 평가 패턴을 조회해 추론을 보정한다.
- **추적성:** `trace_id`가 internal agent diagnostics를 OpenInference 트레이스에 연결한다. retriever span의 document ID는 EvidenceRef 출력으로 grounding된다.

### 8.2 진실 공급원 구분

- `tool_call_logs`는 UI 요약용이다.
- OpenInference 스팬이 트레이스 수준 관측성의 진실 공급원이다.

---

## 9. Core User Flow & Scenarios

### 9.1 핵심 플로우

> **Free Conversation → Context Gathering → Agent Work → Streamed Artifacts → Human Approval → Brief/Calendar → Continuity**

LaunchPilot의 사용자 경험은 버튼으로 고정된 분석 플로우가 아니라 **대화 스트림**이 중심이다. 사용자는 먼저 자유롭게 질문하고, 에이전트가 필요한 맥락과 도구를 선택한다. `Signal → Hypothesis → Experiment → Approval → Brief → Continuity`는 사용자가 따라야 하는 화면 단계가 아니라, Agent Core가 대화 맥락 안에서 수행하는 전문 처리 루프다.

### 9.2 메인 시나리오 — "다음 주에 뭘 테스트하지?" (인플루언서 매니저 Mina)

**배경:** Mina는 크리에이터 Luna의 comeback teaser 캠페인을 담당한다. 금요일 오후, 다음 주 콘텐츠 회의를 앞두고 있다.

**Step 0 — War Room 진입.** Mina는 War Room에 들어온다. 좌측 사이드바에는 캠페인과 과거 브리프가 보이고, 중앙은 자유 대화 main stream, 우측은 문서·실험안·승인 같은 전문 출력 패널이다.

**Step 1 — 자유 질문.** Mina가 composer에 묻는다.
> "이번 캠페인 반응이 애매한데, 다음 주에는 뭘 테스트해야 할까?"

프론트는 이를 `message.send`로 Java에 보낸다. 프론트는 이 문장이 분석 시작인지, 맥락 요청인지, 승인인지 직접 판단하지 않는다.

**Step 2 — 맥락 수집.** Agent Core가 현재 thread, campaign, 과거 brief, 첨부 파일 여부를 보고 필요한 도움을 결정한다. 데이터가 부족하면 자연어로 요청한다.
> "최근 성과 CSV가 있으면 정확히 볼 수 있어요. 리텐션이나 저장률 중심으로 볼까요?"

**Step 3 — 데이터와 지시 첨부.** Mina가 CSV를 첨부하고 다시 말한다.
> "이 CSV 보고 리텐션 중심으로 봐줘."

Java는 CSV를 import해 Elastic에 즉시 인덱싱하고, 이 첨부와 메시지를 Agent Core에 전달한다. 사용자 경험상 주 동작은 계속 `message.send`이며, CSV import는 대화에 필요한 리소스 업로드다.

**Step 4 — 전문 작업 선택.** Agent Core가 필요한 도구와 워커를 선택한다. 예: `query_metric_baseline`, `search_content_posts`, `search_team_notes`, Data Analyst, Strategist, Writer, Reviewer Gate. 프론트는 이 내부 능력 목록을 알 필요가 없다.

**Step 5 — 메시지/block 스트리밍.** Java는 Agent Core의 결과를 main stream 메시지로 보낸다. 메시지 안에는 필요한 block이 들어간다.
- `text`: 사용자에게 설명할 문장
- `activity`: CSV import, 도구 호출, 검증 진행
- `markdown_document`: Evidence notes, Growth Brief 같은 문서
- `artifact`: signal, hypothesis, experiment_plan 같은 구조화 산출물
- `approval`: 저장/캘린더 생성 전 승인 요청
- `result`: 승인 완료 결과
- `error`: 복구 가능한 오류

**Step 6 — 문서와 산출물 표시.** `markdown_document` block을 받으면 중앙 stream에는 작은 문서 카드가 올라가고, 우측 패널은 자동으로 열려 마크다운 본문을 보여준다. 우측 패널은 산출물 리스트를 유지한다. 문서, 확정된 signal, experiment plan, approval result는 문서 제목이 있는 직사각형 카드 버튼으로 누적되고, 사용자가 카드를 클릭하면 해당 산출물의 마크다운 상세가 패널에 표시된다.

**Step 7 — 수정.** Mina가 말한다.
> "실험 제목을 더 짧게, BTS hook 중심으로 바꿔줘."

프론트는 다시 `message.send`만 보낸다. Agent Core가 수정 의도를 해석하고, Java가 업데이트된 artifact block을 스트림에 보낸다. 승인 전 후보는 여전히 React State/세션 타임라인에만 있고, Elastic에는 저장되지 않는다.

**Step 8 — 승인.** 승인이 필요하면 `approval` block이 표시되고 main stream에 승인 표면이 열린다. Mina는 버튼을 눌러도 되고, 자유 대화로 말해도 된다.
> "좋아, 승인할게. 캘린더에 넣어줘."

프론트는 둘 다 `message.send`로 보낸다. 승인 의도 해석은 Agent Core 책임이며, 실제 `growth_briefs`/`calendar_events` 불변 저장은 Java가 열린 approval과 최종 draft를 검증한 뒤 수행한다.

**Step 9 — 확정 결과.** Java는 저장 후 `result` block을 포함한 메시지를 보낸다. 캘린더 화면은 React State로 즉시 렌더링되고, Mina는 생성된 Growth Brief 참조를 완료 receipt에서 확인한다. Growth Brief 마크다운 본문을 우측 패널에 여는 기능은 markdown document block으로 확장한다.

### 9.3 연속 시나리오 — 다음 주, 같은 캠페인 (캠페인 학습 루프)

**1주 후.** Mina가 같은 War Room에 다시 들어와 말한다.
> "지난주 승인한 BTS hook 실험이랑 이어서 보면 이번 주엔 뭘 해야 해?"

Agent Core가 `load_growth_brief_context`로 과거 가설/액션/결과를 복원해 Shared Context에 선주입한다(parent brief가 있을 때 1회). UI는 별도 복원 플로우를 강제하지 않고, stream 메시지와 우측 패널로 연속성 맥락을 보여준다: ① 이전 가설, ② 승인된 액션/실험, ③ 관측된 결과/지표, ④ 다음 분석 질문.

새 추천은 "신규 분석"이 아니라 **지난 실험의 후속**으로 프레이밍된다. 예: "지난주 BTS hook 실험이 save_rate 1.7x를 달성했다. 이번 주는 같은 포맷을 Instagram Reels로 확장 검증한다."

### 9.4 보조 시나리오 — 소규모 기획사 (다채널 비교)

기획사 담당자는 여러 채널 CSV를 한 캠페인으로 올린다. Data Analyst가 채널별 baseline을 분리 집계하고, Instagram의 missed upload 구간과 성장 정체의 상관을 신호로 잡는다. Data Strategist는 "정체는 창작 품질보다 업로드 일관성과 더 강하게 연결" 가설을 만들고, Writer는 일정 채우기 실험을 설계한다.

### 9.5 엣지 시나리오 — 데이터 부족

업로드 콘텐츠가 너무 적으면 Data Analyst가 신뢰 가능한 baseline을 만들 수 없다. 이 경우 워커는 `insufficient_data`를 반환하고, Reviewer Gate는 빈 실험안을 차단(`EMPTY_EXPERIMENT_PLAN`)한다. retry limit 초과 시 Python이 `FAILED`를 반환하고 FE는 복구 가능한 에러 화면(reset/retry)을 보여준다.

---

## 10. Data Model (Elastic 단일 저장소)

상세 스키마는 `contracts/03-java-elastic/documents.schema.json` 참조. **별도 App DB는 없다.** 아래 엔티티는 모두 Elastic 인덱스다.

### 10.1 인덱스 목록

| Index | 목적 | 쓰기 시점 |
|---|---|---|
| `content_posts` | 콘텐츠 성과/포맷/hook/CTA/참여율 | CSV import |
| `follower_logs` | 채널별 팔로워 시계열 | CSV import |
| `campaigns` | 캠페인 목표/단계/기간/타겟 지표 | seed/import |
| `calendar_events` | 업로드 일정, missed event, 승인 실험 일정 | seed import + **승인 시(불변)** |
| `team_notes` | 팬 반응/운영 메모 (v0.1 optional) | seed import |
| `growth_briefs` | 승인된 분석 결과 스냅숏 (시그널/가설/실험/근거) | **승인 시(불변)** |

### 10.2 엔티티 관계

```text
Creator 1 ── N Channel
Creator 1 ── N Campaign
Campaign 1 ── N ContentPost
Campaign 1 ── N CalendarEvent
Campaign 1 ── N TeamNote
Campaign 1 ── N GrowthSignal (런타임, 미저장 — 승인 시 brief에 임베드)
GrowthSignal 1 ── N Hypothesis
Hypothesis 1 ── N ExperimentItem
ExperimentPlan 1 ── N ExperimentItem
ExperimentPlan 1 ── 1 GrowthBrief (승인 시 생성)
AgentThread 1 ── N ToolCallLog / OpenInference span
```

> 시그널·가설·실험 후보는 승인 전까지 어떤 저장소에도 들어가지 않는다(frontend-local). 승인 시 `growth_briefs` 문서 안에 임베드되어 불변 저장된다.

### 10.3 주요 런타임 타입 (frontend-types.ts 기준)

- `Channel`: `youtube | tiktok | instagram | x | unknown`
- `Confidence`: `low | medium | medium_high | high`
- Agent activity is exposed as `activity` blocks, not as a lifecycle enum.
- Approval is exposed as an `approval` block, not as a screen-wide process state.
- `AgentResultPayload`: `{ signals: Signal[], hypotheses: Hypothesis[], experiment_plan: ExperimentPlan }`
- `ExperimentItem`: `{ id, hypothesis_id, title, channel, content_format, hook, cta, target_metric, success_criteria, scheduled_at, production_brief }`

---

## 11. Contracts Map

설계는 `contracts/` 계약 세트로 강제된다.

| 경계 | 폴더 | 주 산출물 |
|---|---|---|
| Frontend ↔ Java | `contracts/01-frontend-java` | `openapi.yaml`(REST), `asyncapi.yaml`(WS), `frontend-types.ts` |
| Java ↔ Python Agent | `contracts/02-java-python-agent` | `openapi.yaml`(REST), `asyncapi.yaml`(WS) |
| Java ↔ Elastic 문서 | `contracts/03-java-elastic` | `documents.schema.json` |
| Python Agent ↔ Elasticsearch MCP | `contracts/04-agent-elastic-mcp` | `evidence-tools.schema.json` |
| ADK 워커 ↔ 구조화 출력 / Reviewer Gate | `contracts/05-agent-output` | `agent-output.schema.json` |
| OpenInference / Phoenix 관측성 | `contracts/06-observability` | `openinference-traces.schema.json` |

실행 가능한 통합 시나리오: `e2e/conversation-first.mock.spec.ts`, `e2e/main-analysis-approval.mock.spec.ts`. 구 run-based `.scenario.json` 파일은 제거되었고, `npm run test:scenarios`는 conversation-first E2E 커버리지 마커를 검증한다.

---

## 12. API / Backend Requirements

### 12.1 공개 API (Frontend ↔ Java)

| Method | Path | 목적 |
|---|---|---|
| POST | `/api/import/csv` | CSV 업로드/파싱/Elastic 인덱싱 |
| WS | `/api/agent/threads/{thread_id}/stream` | 자유 대화 `message.send`, `StreamMessage.blocks[]` 수신 주 채널 |

### 12.2 내부 API (Java ↔ Python)

| Method | Path | 목적 |
|---|---|---|
| POST | `/internal/agent/turns` | Java가 사용자 발화와 thread context를 Agent Core에 전달 |
| WS | `/internal/agent/threads/{thread_id}/stream` | Agent Core → Java user-safe block 출력 스트림 |

### 12.3 Java 매핑 규칙

Java가 프론트에 노출하는 주 스트림 단위는 `StreamMessage`다. 각 메시지는 `sequence`, `role`, `blocks[]`를 갖는다. block은 `text`, `activity`, `markdown_document`, `artifact`, `approval`, `result`, `error` 중 하나이며, 프론트는 block kind에 따라 UI를 렌더링한다.

Java는 Agent Core 출력을 `StreamMessage.blocks[]`로 정규화한다. 승인 게이트는 Java가 소유하며, Agent Core가 자유 발화에서 승인 의도를 감지하더라도 실제 적재 전 Java가 열린 approval과 최종 draft를 검증한다.

Java가 내부로 유지하는 필드: `agent_diagnostics`(worker, validator_passed, backtrack_count, phoenix_reflection_used, trace_id), `started_at/updated_at/completed_at`, raw Python 실패 스택, raw Gemini chunk / chain-of-thought / `thoughtSignature` / function-call transport / raw MCP 메시지.

### 12.4 ID 규약

- `thread_id`: Java 생성, 형식 `run_*`.
- `trace_context.request_id`: Java가 공개 요청마다 생성, 형식 `req_*`.
- `approval_id`: Java 생성(승인 게이트), 형식 `appr_*`.
- `message_id`: Java 생성(대화 메시지), 형식 `msg_*`.
- WS 클라 `message.send.command_id`는 멱등 키 — 서버는 동일 `command_id`를 최대 1회만 실행한다.
- Python은 모든 응답에 `thread_id`를 echo한다.
- 같은 `thread_id` 재시도 → 현재 상태 반환. 다른 body로 재사용 → `409 Conflict`.

---

## 13. Frontend / UI Requirements

상세는 `docs/frontend/screen-architecture.md`, `docs/frontend/state-machine.md` 참조.

### 13.1 레이아웃 원칙

Gemini 스타일의 대화형 쉘이되, 순수 챗 앱은 아니다. 실험 계획과 승인 액션은 메시지 버블 안에 숨지 않고 1급 제품 표면이다.

```text
┌──────────────────────────────────────────────────────────┐
│ Top Bar: LaunchPilot / Campaign / Run Status            │
├──────────┬─────────────────────────────┬───────────────┤
│ Sidebar  │ Main Reasoning Stream       │ Action Panel  │
│ Campaigns│ CSV import & 진행 상태       │ 실험 Draft     │
│ Briefs   │ Signals / Hypotheses         │ 편집 필드      │
│ Lineage  │ Evidence 스니펫              │ Approve 버튼   │
├──────────┴─────────────────────────────┴───────────────┤
│ Composer: 명령/편집/연속 분석 커맨드                      │
└──────────────────────────────────────────────────────────┘
```

그리드: 사이드바 240–280px / 메인 `minmax(420px, 1fr)` / 액션 패널 360–420px / 하단 composer sticky.

### 13.2 프론트 상태 모델 (요약)

프론트는 에이전트 내부 상태 머신을 복제하지 않는다. UI 상태는 다음 축으로 관리한다.

- `messages[]`: main stream의 단일 표시 단위.
- `connection`: WS 연결, replay, full sync, error.
- `composer`: 자유 입력, 첨부, 전송 상태.
- `rightPanel`: 저장된 output cards 목록, 선택된 output id, open 상태. 선택된 산출물은 마크다운 상세로 렌더링한다.
- `draftEdits`: 승인 전 artifact에 대한 로컬 수정.
- `activeWork`: 진행 중인 agent 작업의 표시용 thread id/status/cancellable 여부.

`RUNNING_SIGNAL_DETECTION`, `WAITING_FOR_APPROVAL` 같은 thread status는 전체 화면 상태가 아니라 `activity` 또는 `approval` block의 내용으로 표현한다.

### 13.3 수신 Block별 UI/UX 반응표

프론트가 반응해야 하는 수신 이벤트는 별도 workflow event가 아니라 `StreamMessage.blocks[].kind`다. 같은 메시지 안에 여러 block이 들어올 수 있으며, 프론트는 sequence 순서로 저장한 뒤 block 단위로 UI를 갱신한다.

| 수신 block | 에이전트 경험 | UI 반응 | 우측 패널 | 사용자 개입 |
|---|---|---|---|---|
| `text` | 자유 대화 | main stream에 말풍선/문단으로 표시 | 변경 없음 | composer로 이어서 질문·수정·승인 의사 표현 |
| `activity` | 관찰형 진행 | 도구 사용, 검증, 데이터 처리 상태를 compact row로 표시 | 변경 없음 | 필요 시 “중단해”, “이 기준으로 봐” 같은 `message.send` |
| `markdown_document` | 관찰형 산출 | thread에 작은 문서 카드 표시 | 즉시 open, markdown 본문 렌더 | 문서 내용을 보고 follow-up 질문 또는 수정 요청 |
| `artifact` | 전문 산출 | signal/hypothesis/experiment/brief 요약 카드 표시 | 확정/선택된 산출물을 output card로 누적, 클릭 시 마크다운 상세 표시 | “제목을 줄여줘”, “이 실험 제외해” 같은 `message.send` |
| `approval` | 개입형 게이트 | 승인 필요 카드와 CTA 표시 | 승인 전에는 gate 유지. 승인 후 approval result를 output card로 누적 | 버튼 또는 자유 발화 모두 `message.send(content + optional action)` |
| `result` | 관찰형 완료 | 완료 receipt 표시 | 승인 완료 산출물을 output card로 누적, 클릭 시 생성된 brief/calendar ref 표시 | 후속 질문 또는 이어서 다음 실험 요청 |
| `error` | 개입형 복구 | 오류 row 표시, 복구 가능 여부 노출 | 필요 시 오류 상세 표시 | retry, 다른 지시, 취소를 자연어로 전송 |

품질 기준:

- 관찰형 block은 사용자가 “에이전트가 무엇을 하고 있는지” 이해하게 해야 하지만, 사용자의 흐름을 막지 않는다.
- 개입형 block은 저장, 캘린더 생성, 취소, 복구처럼 결과가 바뀌는 순간에만 강하게 드러난다.
- 모든 개입은 대화로도 가능해야 한다. 버튼은 빠른 입력 수단이며 별도 계약 명령이 아니다.
- 문서와 확정 산출물은 thread에 흔적을 남기고 우측 output panel 리스트에도 누적해, 대화와 전문 출력이 분리되지 않게 한다.

### 13.4 설계 원칙

- 프론트는 Java 공개 API만 호출(Python/Elastic/Gemini/Phoenix 직접 호출 금지).
- 후보 실험안은 승인 전까지 React State/session timeline에만. 사용자 편집은 draft state에만 적용하고, Java 승인 전에는 Elastic에 저장하지 않는다.
- 주 채널은 WebSocket message stream이다. 프론트 수신 단위는 항상 `StreamMessage`이며, message `id` 기준으로 중복을 제거하고 `sequence`는 표시 순서에 사용한다.
- 수신 핸들러는 메시지를 저장하고 message-id dedupe/upsert만 수행한다. 도메인 UI 반응은 `blocks[].kind`별 renderer가 담당한다.

### 13.5 MVP 상호작용 결정

- 사용자 1차 액션은 자유 입력 `message.send`다. CSV 첨부/분석 요청/수정/승인은 모두 메시지 또는 메시지 action으로 표현한다.
- CSV 선택 후에도 사용자는 같은 composer에서 메시지를 보낸다. 분석 시작 여부는 Agent Core가 맥락으로 판단한다.
- 실험 편집은 대화형 수정 요청 또는 우측 패널 draft edit로 가능하다. 버튼 클릭도 최종적으로는 `message.send(action)`로 수렴한다.

### 13.6 시각 시스템 (Apple 절제)

white/off-white/pearl/near-black 표면, 단일 quiet blue 액션 컬러, 절제된 chrome, 명료한 타이포. 마케팅 히어로/장식 그라데이션/무거운 그림자/중첩 카드 지양. 데이터·근거·실험안이 첫 화면 주역.

---

## 14. AI Output Schema & Validation

### 14.1 워커별 중간 스키마 → 단일 최종 payload

```text
Data Analyst   → SignalDraftOutput
Data Strategist→ HypothesisDraftOutput
Data Writer    → ExperimentPlanDraftOutput
Reviewer Gate  → ValidationReport
Assembler      → AgentResultPayload   (canonical)
```

### 14.2 Canonical Final Payload 예시

```json
{
  "signals": [
    {
      "id": "sig_001",
      "type": "content_outperformance",
      "title": "BTS shorts outperformed recent baseline",
      "description": "Two behind-the-scenes TikTok shorts showed save rates 2.8x above the 30-day channel baseline.",
      "metric_name": "save_rate",
      "current_value": 0.074,
      "baseline_value": 0.026,
      "lift_ratio": 2.8,
      "date_window": { "start": "2026-05-25", "end": "2026-06-01" },
      "confidence": "high",
      "evidence_refs": ["post_014", "post_017", "metric_20260601_001"]
    }
  ],
  "hypotheses": [
    {
      "id": "hyp_001",
      "signal_ids": ["sig_001"],
      "statement": "Raw behind-the-scenes clips may be converting passive viewers into deeper engagement better than polished teaser assets.",
      "rationale": "The strongest posts share the BTS angle and face-first hook, and team notes mention strong fan reaction to raw practice footage.",
      "confidence": "medium_high",
      "supporting_evidence_refs": ["post_014", "post_017", "note_006"],
      "caveats": ["External fan community activity was not measured.", "This is a correlation, not a causal claim."]
    }
  ],
  "experiment_plan": {
    "id": "plan_001",
    "summary": "Next week should test whether the same raw BTS format reproduces engagement uplift across TikTok and Instagram.",
    "overall_confidence": "medium_high",
    "items": [
      {
        "id": "exp_001",
        "hypothesis_id": "hyp_001",
        "title": "BTS face-first hook test",
        "channel": "tiktok",
        "content_format": "12-second short",
        "hook": "Open with a close-up reaction in the first 2 seconds.",
        "cta": "Ask fans to comment which practice moment they want next.",
        "target_metric": "save_rate",
        "success_criteria": "save_rate >= 1.5x TikTok 30-day baseline within 48 hours",
        "scheduled_at": "2026-06-03T20:00:00+09:00",
        "production_brief": "Use raw rehearsal footage, minimal polish, subtitles on-screen."
      }
    ]
  }
}
```

### 14.3 검증 규칙

- `signals[].evidence_refs` ⊆ 알려진 EvidenceRef ID.
- `hypotheses[].supporting_evidence_refs` ⊆ 알려진 EvidenceRef ID.
- `hypotheses[].signal_ids` → 존재하는 signal 참조.
- `experiment_plan.items[].hypothesis_id` → 존재하는 hypothesis 참조.
- 각 experiment는 `target_metric`, `success_criteria` 보유.
- 각 hypothesis는 caveat 최소 1개.
- snake_case 필드, 계약 정의 ID prefix 사용.
- raw Gemini reasoning / raw Elastic 문서 / ES|QL / DSL / MCP 전송 메시지 / provider 오류 본문 금지.

### 14.4 System Prompt 핵심 규칙 (전 워커 공유 골격)

```text
You are part of LaunchPilot, a multi-agent growth interpreter for creator teams.
Turn social performance data into signals, hypotheses, and next-week content experiments.
Never claim causality. Use evidence-based, correlation-aware language.
Every hypothesis must include confidence, supporting evidence, and caveats.
Do not modify calendar or report data; human approval happens outside this agent.
If evidence is insufficient, return insufficient_data.
Only use evidence_refs that evidence tools actually returned.
Return strictly valid JSON following the provided draft schema.
```

---

## 15. Safety, Accuracy, and Trust

| 원칙 | 제품 동작 |
|---|---|
| No causal overclaim | "caused" 대신 "associated with / linked to / candidate driver" |
| Evidence-first | 모든 signal/hypothesis에 evidence_refs |
| Confidence 표시 | high / medium_high / medium / low |
| 데이터 부족 처리 | `insufficient_data` 명시 |
| Deterministic gate | Reviewer Gate 결정적 검증 통과 후에만 노출, Gemini가 뒤집지 못함 |
| Human approval | 승인 전 calendar/brief 변경 금지(Python은 승인 처리 안 함) |
| Transparency | Evidence Drawer + tool_call_logs + OpenInference 트레이스 |
| Reproducibility | 동일 입력에서 동일 흐름 재현, demo reset 지원 |

### Confidence 루브릭

| Confidence | 조건 |
|---|---|
| high | 동일 패턴 콘텐츠 2개 이상, baseline 대비 2x 이상, 관련 메모/캘린더 근거 존재 |
| medium_high | 성과·시간 정렬 강하나 외부 이벤트 근거 부족 |
| medium | signal은 있으나 반복성/문맥 근거 약함 |
| low | 데이터 부족 또는 conflicting evidence |

### 금지/허용 표현

- 금지: "이 영상이 팔로워 증가를 만들었습니다."
- 허용: "이 영상은 해당 성장 구간과 가장 강하게 연결된 원인 후보입니다. 같은 기간 지표와 팀 메모를 함께 보면 BTS 포맷 가설을 다음 주에 검증할 가치가 있습니다."

---

## 16. MVP Scope

### 16.1 Must-have
| 기능 | 설명 |
|---|---|
| CSV import | 스트리밍 파싱 → Elastic 즉시 인덱싱(`refresh=true`) |
| Elastic 단일 저장소 | content_posts/follower_logs/campaigns/calendar_events/team_notes/growth_briefs |
| 4-Agent 파이프라인 | Analyst → Strategist → Writer → Reviewer Gate + Orchestrator |
| Evidence Wrapper 도구 | search_content_posts, query_metric_baseline, search_team_notes, load_growth_brief_context |
| 대화형 WS 스트리밍 | message.send 송신 + StreamMessage.blocks[] 수신, message id 기반 중복 제거 + sequence 기반 정렬 |
| Reviewer Gate 검증 | 결정적 스키마/근거 검증 + 백트래킹 |
| Human Approval | 승인 전 미저장, 승인 시 불변 적재 |
| Growth Brief + Calendar | 승인 시 growth_briefs 1 + calendar_events N |
| Evidence Drawer / tool log | 근거·도구 호출 시각화 |
| OpenInference 트레이싱 | LLM/도구/Gate 스팬 송신 |
| 연속성(parent_brief_id) | 캠페인 학습 루프 복원 |

### 16.2 Nice-to-have
- Phoenix MCP 자가 성찰 데모 노출
- Slack webhook, PDF export, 편집 가능한 실험안
- Multi-creator workspace, 공유 가능한 public link

### 16.3 Out of scope
- Instagram/TikTok/X 실시간 API, 자동 게시, 광고 최적화
- Full SaaS billing/auth, 멀티 워크스페이스 권한, 경쟁사 벤치마킹

---

## 17. Hackathon Demo Scenario (3분)

### 17.1 심사위원이 이해해야 할 것
1. LaunchPilot은 챗봇이 아니라 **역할 분리 멀티 에이전트** 워룸이다.
2. Elastic이 유일 저장소이자 evidence engine이다(Elasticsearch MCP).
3. 4개 워커가 신호→가설→실험을 분담하고 Reviewer Gate가 검증한다.
4. 사용자가 승인하면 불변 캘린더/브리프가 생성된다.
5. 모든 추론이 OpenInference로 추적된다.

### 17.2 데모 스크립트

| 시간 | 화면 | 내레이션 |
|---|---|---|
| 0:00–0:20 | War Room (idle) | "크리에이터 팀은 분석은 있지만 해석이 없습니다. 무엇이 바뀌었고, 왜이고, 다음에 뭘 테스트할지." |
| 0:20–0:40 | CSV import | "60일 comeback 캠페인 CSV를 올리면 Java가 Elastic에 즉시 인덱싱합니다." |
| 0:40–1:05 | Analyze + tool log | "버튼 하나로 4개 ADK 워커 파이프라인이 시작됩니다. Analyst가 Elastic MCP로 baseline을 계산합니다." |
| 1:05–1:35 | Signal Cards | "BTS short가 baseline 2.8배, 댓글 CTA가 1.9배, Instagram missed upload 정체 — 3개 신호." |
| 1:35–2:00 | Hypothesis Panel | "Strategist가 근거 기반 가설을 만듭니다. 인과 단정이 아니라 confidence와 caveat 포함." |
| 2:00–2:25 | Experiment Plan | "Writer가 다음 주 실험 3개를 설계하고, Reviewer Gate가 근거 무결성을 검증합니다." |
| 2:25–2:45 | Approve | "사용자가 검토·수정 후 승인하면 불변 캘린더와 브리프가 생성됩니다." |
| 2:45–3:00 | Brief + Trace | "추론 경로는 OpenInference 트레이스로 추적됩니다. Gemini + Google ADK + Elastic MCP + Phoenix." |

---

## 18. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Elastic MCP 연동 실패 | 파트너 도구 미사용처럼 보임 | wrapper backend fallback + MCP 연결 로그 우선 구현 |
| Gemini 출력 불안정 | UI 파싱 실패 | draft 스키마 검증, Reviewer Gate 백트래킹, deterministic fallback |
| 워커 간 상태 누수 | 잘못된 evidence_ref | Shared Context 격리 + ref 집합 검사 |
| seed/CSV 데이터가 인위적 | 실무성 약화 | noise·mixed signal·missed upload·conflicting evidence 포함 |
| 데모 지연 | 3분 실패 | precomputed result cache, skeleton loading, demo 모드 |
| 단일 DB 부하 | 인덱싱 지연 | Serverless autoscale + 데모 규모 제한 |
| causal 과장 | 신뢰도 하락 | wording 강제 + Reviewer Gate `UNSAFE_OR_UNGROUNDED_CLAIM` |
| UI가 대시보드처럼 보임 | 에이전트성 약화 | 추론 스트림·tool log·실험안 중앙 배치 |
| 기존 프로젝트 확장 오해 | 규칙 리스크 | 새 repo/앱명/UI/dataset, 운영 DB 미사용 |

---

## 19. Milestones

| 기간 | 산출물 | 완료 기준 |
|---|---|---|
| Day 1–2 | 새 repo, 3-컨테이너 skeleton, seed/CSV dataset, demo reset | 로컬 실행, CSV import API가 Elastic에 인덱싱 |
| Day 3–4 | Elastic Serverless 프로젝트, 인덱스 매핑, ES|QL/하이브리드 검색, Evidence wrapper 4종 | 4개 wrapper 도구 정상 작동 |
| Day 5–7 | ADK 4-워커 + Orchestrator + Reviewer Gate, Gemini 구조화 출력, OpenInference 트레이싱 | "What should we test next week?" 실행 시 검증 통과한 payload 생성 |
| Day 8–10 | War Room 3영역 UI, Signal/Evidence/Hypothesis/Experiment 패널, Approval, Calendar/Brief 뷰 | 해피패스 클릭만으로 끝까지 진행 |
| Day 11–12 | loading/error 상태, tool log 애니메이션, deterministic fallback, 연속성 플로우 | 지연 시에도 데모 미실패, reset 후 3분 재현 |
| Day 13–14 | hosted URL, public repo, README, 3분 데모 영상, Devpost | 제3자가 README만 보고 실행 가능 |

---

## 20. Open Questions

1. Reviewer Gate retry limit 정확한 값.
2. formatter 단계를 별도 `LlmAgent`로 둘지 결정적 Python normalization으로 둘지.
3. Gemini 보조 repair를 데모에 켤지 deferral.
4. `team_notes`에 Java 소유 문서 계약을 줄지 demo seed로 둘지.
5. 내부 서비스 인증(`X-Internal-Token`) 데모 적용 여부.
6. Growth Brief export markdown copy까지만 vs PDF.
7. confidence를 rule-based vs Gemini 제안 + backend 검증.
8. demo video에서 OpenInference 트레이스를 얼마나 노출할지.

---

## Appendix A. Demo Seed Data Design

### A.1 Campaign
- Name: Luna Comeback Teaser Campaign
- Objective: follower_growth + engagement
- Phase: teaser
- Date range: 2026-05-01 ~ 2026-06-07
- Primary metric: follower_delta / Secondary: save_rate, comment_rate

### A.2 의도된 숨은 패턴
1. BTS/raw 연습 클립이 polished teaser보다 성과 우위.
2. 댓글 CTA는 댓글을 늘리지만 항상 팔로워 성장으로 이어지지 않음.
3. Instagram missed upload가 성장 정체와 상관.
4. YouTube Shorts가 TikTok 급등 24–48시간 후 지연 lift.

### A.3 Agent 기대 출력
- Signals: TikTok BTS save_rate 2.8x / 댓글 CTA comment_rate 1.9x / Instagram missed 2 reels during flat growth
- Hypotheses: raw BTS 반복 가능한 engagement driver / 댓글 CTA는 즉시 전환보다 커뮤니티 반응 / Instagram 정체는 일정 일관성 문제
- Experiments: TikTok BTS face-first hook test / Instagram repurposed BTS reel test / fan comment reply format test

---

## Appendix B. Developer Implementation Order

**P0**
1. CSV import → Elastic 인덱싱
2. Evidence wrapper 4종 (Elasticsearch MCP)
3. Data Analyst Worker (정량 신호)
4. Data Strategist + Data Writer Worker
5. Reviewer Gate + Orchestrator 백트래킹
6. Java thread WebSocket + StreamMessage block 정규화 + sequence 부여
7. War Room UI 해피패스
8. Approval → growth_briefs/calendar_events 불변 적재
9. OpenInference 트레이싱

**P1**
1. 연속성(parent_brief_id) 복원
2. Phoenix MCP 자가 성찰
3. Evidence Drawer polish, tool log
4. Growth Brief markdown export
5. demo reset

**P2**
1. Slack webhook, PDF export
2. 편집 가능한 실험안
3. Multi-creator workspace
