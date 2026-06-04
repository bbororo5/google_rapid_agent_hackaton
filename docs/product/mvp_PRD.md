# LaunchPilot PRD
## Growth Signal-to-Experiment Agent

| 항목 | 내용 |
|---|---|
| 문서 버전 | v0.1 Hackathon PRD |
| 작성일 | 2026-05-29 |
| 제출 목적 | Google Cloud Rapid Agent Hackathon 신규 프로젝트 개발 문서 |
| Partner Track | Elastic |
| AI / Agent | Gemini + Google Cloud Agent Builder |
| 핵심 제품 루프 | Signal → Hypothesis → Experiment → Action → Report |
| 제출 원칙 | 기존 운영 서비스의 수정/확장이 아닌 새 repo, 새 코드베이스, 새 demo dataset |

---

## 1. Executive Summary

### 1.1 제품명

**LaunchPilot**

### 1.2 한 줄 설명

LaunchPilot은 크리에이터 팀의 흩어진 SNS 성장 데이터를 해석해, 중요한 성장 신호를 찾고, 원인 가설을 세우며, 다음 주 검증 가능한 콘텐츠 실험안으로 바꿔주는 AI 에이전트다.

### 1.3 핵심 사용자

1차 타겟은 다음 네 그룹이다.

| 사용자 | 핵심 상황 |
|---|---|
| 소규모 기획사 | 여러 아티스트/크리에이터의 콘텐츠 성과를 관리하고 다음 콘텐츠 전략을 정해야 함 |
| 인플루언서 매니저 | 담당 크리에이터의 주간 성과를 해석하고 클라이언트/대표에게 보고해야 함 |
| 1~5인 크리에이터 팀 | 여러 SNS 채널 데이터를 엑셀·노션·수동 캡처로 관리하며 다음 콘텐츠를 감으로 정함 |
| 브랜드 SNS 담당자 | 캠페인별 ROI와 다음 A/B 테스트 방향을 설명해야 함 |

2차 타겟은 콘텐츠가 최소 30개 이상 쌓인 성장 중인 개인 크리에이터다.

### 1.4 핵심 문제

사용자는 SNS 데이터를 볼 수는 있지만, 다음 질문에 명확히 답하지 못한다.

- 이번 주 데이터에서 진짜 중요한 변화는 무엇인가?
- 어떤 콘텐츠가 성장 변화와 가장 강하게 연결되어 있는가?
- 이 변화는 우연인가, 반복 가능한 신호인가?
- 다음 주에는 무엇을 A/B 테스트해야 하는가?
- 팀이나 클라이언트에게 이 결과를 어떻게 설명해야 하는가?

### 1.5 핵심 가치

LaunchPilot은 단순 대시보드나 주간 리포트 생성기가 아니다. 사용자가 직접 차트를 읽고 회의에서 해석해야 했던 과정을 다음 흐름으로 압축한다.

> **Signal → Hypothesis → Experiment → Action → Report**

즉, 제품의 최종 결과물은 “지난주 요약”이 아니라 **다음 주 실행 가능한 콘텐츠 실험안**이다.

### 1.6 해커톤 제출 전략

- **Track:** Elastic
- **핵심 차별점:** Elastic을 evidence engine으로 사용해 구조화된 SNS 성과 데이터와 비구조화된 팀 메모/과거 리포트를 함께 검색한다.
- **에이전트성 증명:** Gemini 기반 에이전트가 데이터를 검색하고, 신호를 감지하고, 가설을 생성하고, 실험안을 설계하고, 승인 후 캘린더와 Growth Brief를 생성한다.
- **데모 전략:** 실제 SNS API 연동은 MVP에서 제외한다. Seed data 또는 CSV import로 안정적인 3분 데모를 구성한다.

---

## 2. Problem Definition

### 2.1 사용자의 현재 업무 방식

소규모 크리에이터 팀과 매니저는 보통 다음 방식으로 일한다.

1. Instagram, TikTok, YouTube, X 등 여러 앱에서 성과 수치를 확인한다.
2. 조회수, 좋아요, 댓글, 저장, 팔로워 변화를 엑셀·노션·스프레드시트에 옮긴다.
3. 잘 된 콘텐츠와 안 된 콘텐츠를 사람이 눈으로 비교한다.
4. 회의에서 “왜 잘 됐는지”를 감으로 해석한다.
5. 다음 주 콘텐츠 아이디어를 브레인스토밍한다.
6. 클라이언트/대표에게 보고서를 만든다.

이 과정의 병목은 데이터 수집만이 아니다. 더 큰 병목은 **데이터 해석과 다음 실험 설계**다.

### 2.2 기존 SNS 분석 도구의 한계

Later, Metricool, Sprout Social류의 도구는 성과를 보여주는 데 강하다. 하지만 사용자가 원하는 실무 질문은 다음에 가깝다.

- “이 숫자에서 뭘 봐야 하는가?”
- “왜 이 콘텐츠가 튄 것으로 보이는가?”
- “다음 주에 어떤 실험을 해야 하는가?”
- “보고서에 어떤 문장으로 설명해야 하는가?”

기존 대시보드는 차트를 제공하지만, **차트에서 실험안으로 넘어가는 사고 과정**을 자동화하지 않는다.

### 2.3 LaunchPilot이 해결하는 Pain Point

| Pain Point | LaunchPilot의 해결 방식 |
|---|---|
| 숫자는 많은데 중요한 변화가 무엇인지 모름 | 성장 신호를 자동 감지하고 Signal Card로 요약 |
| 콘텐츠와 성장 변화의 관계를 해석하기 어려움 | Elastic에서 콘텐츠 성과, 캠페인 단계, 캘린더, 팀 메모를 함께 검색 |
| 원인 추정이 감에 의존함 | 근거 카드와 confidence를 포함한 가설 생성 |
| 다음 콘텐츠 아이디어가 감으로 나옴 | 검증 가능한 Experiment Plan 생성 |
| 보고서 작성 시간이 오래 걸림 | “신호 → 가설 → 실험” 중심의 1페이지 Growth Brief 생성 |

### 2.4 해결하지 않는 문제

MVP에서 다음 문제는 해결하지 않는다.

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
- 문제: 매주 어떤 콘텐츠가 반응을 만들었는지 정리하고 다음 콘텐츠 방향을 잡아야 한다.
- JTBD: “캠페인 회의 전에, 어떤 콘텐츠 포맷을 더 테스트해야 하는지 근거와 함께 정리하고 싶다.”

#### B. 인플루언서 매니저

- 상황: 담당 크리에이터의 채널 성장을 주간 단위로 보고한다.
- 문제: 단순 수치 요약은 가능하지만, 왜 성장했는지와 다음 액션을 설명하기 어렵다.
- JTBD: “주간 성과 데이터를 보고, 클라이언트에게 설명 가능한 성장 신호와 다음 실험안을 만들고 싶다.”

#### C. 1~5인 크리에이터 팀

- 상황: 기획자, 편집자, 출연자가 소규모로 운영한다.
- 문제: SNS별 인사이트를 보지만 다음 주 콘텐츠 계획은 감으로 정한다.
- JTBD: “지난 콘텐츠 성과를 바탕으로 다음 주에 무엇을 실험할지 빠르게 결정하고 싶다.”

### 3.2 2차 타겟

#### 성장 중인 개인 크리에이터

- 조건: 최근 60일 내 콘텐츠 30개 이상, 주 3회 이상 업로드.
- 문제: 스스로 데이터를 해석하기 어렵고, 어떤 포맷을 반복해야 할지 모른다.
- JTBD: “내 계정에서 반복되는 성장 신호를 찾아 다음 콘텐츠 아이디어로 바꾸고 싶다.”

---

## 4. Product Positioning

### 4.1 이 제품이 아닌 것

LaunchPilot은 다음이 아니다.

- 단순 SNS 대시보드
- 단순 AI 챗봇
- 단순 주간 보고서 생성기
- 단순 캡션 생성기
- 자동 게시 도구
- API 연동 중심 데이터 파이프라인 도구

### 4.2 이 제품인 것

LaunchPilot은 **Signal-to-Experiment Agent**다.

사용자가 데이터를 읽는 대신, 에이전트가 다음 작업을 수행한다.

1. 데이터를 검색한다.
2. 중요한 신호를 찾는다.
3. 신호와 관련된 근거를 모은다.
4. 원인 후보를 가설화한다.
5. 다음 주 실험안을 만든다.
6. 사용자 승인 후 캘린더와 보고서를 생성한다.

### 4.3 경쟁 도구와의 차별점

| 구분 | 일반 SNS 분석 도구 | LaunchPilot |
|---|---|---|
| 중심 가치 | 성과 시각화 | 데이터 해석과 실험 설계 |
| 사용자 역할 | 차트를 보고 직접 판단 | 에이전트가 신호와 가설을 제안 |
| 결과물 | 대시보드, 리포트 | 실험 계획, 캘린더, Growth Brief |
| AI 역할 | 요약 또는 Q&A | 멀티스텝 에이전트 |
| 근거 제시 | 제한적 | Evidence Drawer로 근거 표시 |
| 실행성 | 낮음 | 승인 후 캘린더 반영 |

---

## 5. Core User Flow

### 5.1 핵심 플로우

> **Signal → Hypothesis → Experiment → Action → Report**

### 5.2 사용자 시나리오

#### Step 0. Demo dataset 선택

사용자는 “Comeback Teaser Campaign” 데모 데이터셋을 선택한다.

데이터셋에는 다음이 포함된다.

- 60일 팔로워 로그
- 45개 콘텐츠 포스트
- 1개 활성 캠페인
- 18개 캘린더 이벤트
- 10개 팀 메모
- 3개 과거 Growth Brief
- 의도적으로 심어진 성장 급등/정체/업로드 공백 이벤트

#### Step 1. 사용자가 질문 실행

사용자가 선택한 캠페인의 Experiment Planner 작업 공간에서 버튼을 누른다.

> **What should we test next week?**

#### Step 2. 에이전트가 데이터 검색

LaunchPilot Agent는 Elastic tools를 호출한다.

1. 최근 30일 콘텐츠 평균 성과 조회
2. 최근 7일 성장 변화 조회
3. 성장 급등 구간과 같은 시간대의 게시물 검색
4. 캠페인 단계 검색
5. 팀 메모에서 팬 반응 관련 문장 검색
6. 캘린더에서 missed event 확인

#### Step 3. 성장 신호 생성

에이전트가 최소 3개의 Signal Card를 만든다.

예:

1. TikTok BTS short 2개가 최근 30일 평균 대비 저장률 2.8배.
2. 댓글형 CTA가 포함된 콘텐츠의 댓글률이 평균 대비 1.9배.
3. Instagram은 scheduled reel 2개가 missed 상태인 기간에 성장률이 정체.

#### Step 4. 가설 생성

에이전트가 2~3개의 hypothesis를 만든다.

예:

- Hypothesis A: 팬들은 polished teaser보다 raw behind-the-scenes short에 더 강하게 반응했을 가능성이 있다.
- Hypothesis B: 댓글 참여를 유도하는 CTA가 팔로워 전환보다 커뮤니티 반응을 먼저 끌어올렸을 가능성이 있다.
- Hypothesis C: Instagram 정체는 콘텐츠 포맷 문제보다 업로드 공백과 더 강하게 연결되어 있을 수 있다.

각 가설은 evidence_refs, confidence, caveat를 포함한다.

#### Step 5. 실험안 생성

에이전트가 다음 주 실험안 3개를 생성한다.

각 실험안에는 다음이 포함된다.

- 실험명
- 검증할 가설
- 채널
- 콘텐츠 포맷
- hook
- CTA
- 업로드 일정
- 목표 지표
- 성공 기준
- 실패 시 해석 기준
- 필요한 제작 브리프

#### Step 6. 사용자 승인

사용자가 “Approve experiments”를 클릭한다.

#### Step 7. Action 수행

승인 후 시스템은 다음을 생성한다.

- calendar_events 3~4개
- experiment_plan record
- growth_brief record
- agent_action_logs

#### Step 8. Report 생성

Growth Brief View에서 다음 항목을 보여준다.

- Executive summary
- Top 3 signals
- Hypotheses
- Next week experiments
- Calendar plan
- Evidence appendix

---

## 6. MVP Scope

### 6.1 Must-have

| 기능 | 설명 |
|---|---|
| Seed data import | 데모용 캠페인 데이터 자동 생성 및 초기화 |
| CSV import | 선택 기능이지만 최소 1개 CSV 업로드 흐름 제공 |
| Elastic indexing | follower_logs, content_posts, campaigns, calendar_events, team_notes, growth_briefs 인덱싱 |
| Growth Signal Detection | 최근 평균 대비 튄 성과, 성장 급등/정체, 업로드 공백 탐지 |
| Evidence Search | Signal과 관련된 콘텐츠/메모/캘린더/캠페인 근거 검색 |
| Hypothesis Generation | evidence 기반 가설 생성, confidence 포함 |
| Experiment Plan Generator | 다음 주 검증 가능한 콘텐츠 실험안 생성 |
| Approval Flow | 사용자 승인 전에는 캘린더/보고서 변경 금지 |
| Calendar Update | 승인 후 실험 일정을 캘린더에 반영 |
| One-page Growth Brief | 팀/클라이언트 공유용 1페이지 브리프 생성 |
| Agent tool call log / Evidence drawer | 에이전트가 어떤 근거를 사용했는지 시각화 |
| Demo Reset | 데모 상태를 초기 seed로 되돌리는 기능 |

### 6.2 Nice-to-have

- Slack webhook
- PDF export
- Multi-creator workspace
- Content caption drafts
- Shareable public report link

### 6.3 Out of scope

- Instagram/TikTok/X full API integration
- Real-time data collection
- Full SaaS billing/auth
- Advanced predictive modeling
- Autonomous posting
- Paid ad optimization
- Competitor benchmarking

---

## 7. Functional Requirements

### 7.1 Data Import

| 항목 | 내용 |
|---|---|
| Feature name | Data Import |
| User story | 사용자는 데모 데이터 또는 CSV를 불러와 바로 에이전트 분석을 실행하고 싶다. |
| Description | seed dataset 또는 CSV 파일을 app DB에 저장하고 Elastic index에 동기화한다. |
| Input | dataset_id 또는 CSV files |
| Process | 파일 검증 → schema mapping → app DB upsert → Elastic bulk indexing → import summary 생성 |
| Output | imported counts, validation errors, indexing status |
| Edge cases | 필수 컬럼 누락, 날짜 형식 오류, 중복 post_id, 빈 파일 |
| Acceptance criteria | seed import 후 최소 60개 follower_logs, 45개 content_posts, 18개 calendar_events, 10개 team_notes가 생성된다. |

### 7.2 Elastic Indexing

| 항목 | 내용 |
|---|---|
| Feature name | Elastic Indexing |
| User story | 에이전트가 SNS 데이터와 팀 메모를 빠르게 검색할 수 있어야 한다. |
| Description | App DB의 주요 엔티티를 Elastic index로 동기화한다. |
| Input | app DB records |
| Process | normalize → enrich fields → bulk index → refresh index |
| Output | index status, indexed document counts |
| Edge cases | Elastic 연결 실패, partial indexing, mapping mismatch |
| Acceptance criteria | 모든 must-have index에서 검색 가능한 document가 존재한다. |

### 7.3 Signal Detection

| 항목 | 내용 |
|---|---|
| Feature name | Growth Signal Detection |
| User story | 사용자는 이번 주 데이터에서 무엇을 봐야 할지 알고 싶다. |
| Description | 최근 7일과 최근 30일 baseline을 비교해 의미 있는 변화 후보를 찾는다. |
| Input | date_range, campaign_id, channels |
| Process | follower delta 계산 → content metric baseline 계산 → anomaly candidate 추출 → signal ranking |
| Output | GrowthSignal[] |
| Edge cases | 데이터 부족, reach=0, 신규 채널, outlier 과다 |
| Acceptance criteria | demo dataset 기준 최소 3개의 signal이 생성된다. |

### 7.4 Evidence Search

| 항목 | 내용 |
|---|---|
| Feature name | Evidence Search |
| User story | 사용자는 에이전트가 왜 그런 결론을 냈는지 확인하고 싶다. |
| Description | 각 signal에 관련된 콘텐츠, 팀 메모, 캠페인, 캘린더 이벤트를 Elastic에서 검색한다. |
| Input | signal_id, date_window, query_terms |
| Process | ES|QL aggregation + semantic search → evidence ranking → evidence_refs 생성 |
| Output | EvidenceRef[] |
| Edge cases | 관련 메모 없음, 검색 결과 과다, 시간대 불일치 |
| Acceptance criteria | 각 signal은 최소 2개의 evidence_ref를 가진다. |

### 7.5 Hypothesis Generation

| 항목 | 내용 |
|---|---|
| Feature name | Hypothesis Generation |
| User story | 사용자는 성장 변화의 가능한 원인을 가설 형태로 알고 싶다. |
| Description | Gemini가 signal과 evidence를 바탕으로 원인 후보를 가설로 작성한다. |
| Input | signals[], evidence_refs[] |
| Process | prompt with constraints → structured JSON generation → validation → confidence scoring |
| Output | Hypothesis[] |
| Edge cases | 근거 부족, conflicting evidence, Gemini JSON 파싱 실패 |
| Acceptance criteria | 각 hypothesis는 confidence, supporting_evidence_ids, caveats를 포함한다. |

### 7.6 Experiment Plan Generation

| 항목 | 내용 |
|---|---|
| Feature name | Experiment Plan Generator |
| User story | 사용자는 다음 주에 무엇을 A/B 테스트해야 할지 구체적으로 알고 싶다. |
| Description | 가설을 검증 가능한 콘텐츠 실험안으로 변환한다. |
| Input | hypotheses[], campaign constraints, available dates |
| Process | experiment design → metric selection → success criteria generation → schedule draft |
| Output | ExperimentPlan with ExperimentItem[] |
| Edge cases | 일정 부족, 채널 데이터 부족, 목표 지표 불명확 |
| Acceptance criteria | 실험안은 최소 3개 item을 포함하고 각 item은 target_metric과 success_criteria를 가진다. |

### 7.7 Human Approval

| 항목 | 내용 |
|---|---|
| Feature name | Human Approval |
| User story | 사용자는 에이전트가 만든 계획을 검토한 뒤 승인하고 싶다. |
| Description | 캘린더와 리포트 생성 전 승인 모달을 띄운다. |
| Input | experiment_plan_id, user decision |
| Process | pending plan 표시 → approve/edit/reject → action log 기록 |
| Output | approved_plan or rejected_plan |
| Edge cases | 중복 승인, 승인 전 데이터 변경, plan expired |
| Acceptance criteria | 승인 전에는 calendar_event와 growth_brief가 생성되지 않는다. |

### 7.8 Calendar Action

| 항목 | 내용 |
|---|---|
| Feature name | Calendar Action |
| User story | 사용자는 승인한 실험안을 바로 콘텐츠 캘린더에 반영하고 싶다. |
| Description | approved experiment items를 calendar_events로 생성한다. |
| Input | approved experiment_plan_id |
| Process | schedule validation → calendar_event insert → action log |
| Output | created calendar_events[] |
| Edge cases | 날짜 충돌, 과거 날짜, 중복 일정 |
| Acceptance criteria | 승인 후 최소 3개의 calendar_event가 생성된다. |

### 7.9 Growth Brief Report

| 항목 | 내용 |
|---|---|
| Feature name | Growth Brief Report |
| User story | 사용자는 팀/클라이언트에게 공유할 수 있는 1페이지 브리프가 필요하다. |
| Description | signal, hypothesis, experiment plan을 요약한 report를 생성한다. |
| Input | approved experiment_plan_id, signals, hypotheses |
| Process | report JSON generation → markdown/html render → save to DB |
| Output | GrowthBrief |
| Edge cases | 일부 근거 없음, plan rejected, report regeneration |
| Acceptance criteria | Growth Brief는 summary, signals, hypotheses, experiments, evidence appendix를 포함한다. |

### 7.10 Demo Reset

| 항목 | 내용 |
|---|---|
| Feature name | Demo Reset |
| User story | 데모 중 언제든 초기 상태로 돌아가고 싶다. |
| Description | app DB와 Elastic index를 seed baseline으로 되돌린다. |
| Input | dataset_id |
| Process | delete demo workspace data → reimport seed → reindex Elastic |
| Output | reset status |
| Edge cases | reset 중 agent run 실행, Elastic delete 실패 |
| Acceptance criteria | reset 후 동일한 agent run 결과를 재현할 수 있다. |

---

## 8. Agent Design

### 8.1 Agent name

**LaunchPilot Agent**

### 8.2 Agent responsibilities

- Growth signal 탐지
- Evidence 검색
- Hypothesis 생성
- Experiment plan 설계
- 사용자 승인 대기
- 승인된 action 실행
- Growth Brief 생성
- Tool call log 저장

### 8.3 Agent operating principles

1. 근거 없는 결론을 내리지 않는다.
2. causal claim을 피하고 correlation/evidence wording을 사용한다.
3. 모든 hypothesis에는 confidence와 caveat를 포함한다.
4. 실행 action은 사용자 승인 후에만 수행한다.
5. 데이터가 부족하면 insufficient data를 반환한다.

### 8.4 Agent tools

| Tool | 목적 | Input | Output | 사용 시점 |
|---|---|---|---|---|
| search_content_posts | 콘텐츠 성과와 포맷 검색 | query, channel, date_range, campaign_id | content_posts[] | signal 탐지 및 evidence 검색 |
| query_follower_growth | 팔로워 변화 계산 | channel, date_range | growth_series, deltas | signal 탐지 |
| search_campaign_context | 캠페인 단계/목표/기간 조회 | campaign_id, date_range | campaign context | hypothesis 생성 전 |
| search_team_notes | 팀 메모 semantic search | query, date_range, entity_type | team_notes[] | evidence 보강 |
| detect_growth_signals | baseline 대비 변화 추출 | campaign_id, date_range | GrowthSignal[] | agent run 초기 |
| generate_hypotheses | signal과 evidence로 가설 생성 | signals, evidence | Hypothesis[] | signal 후 |
| generate_experiment_plan | 가설을 실험안으로 변환 | hypotheses, constraints | ExperimentPlan | hypothesis 후 |
| apply_approved_plan | 승인된 계획 실행 | experiment_plan_id | calendar_events, action_logs | 사용자 승인 후 |
| generate_growth_brief | 1페이지 브리프 생성 | signals, hypotheses, plan | GrowthBrief | action 후 |

### 8.5 Agent run state machine

```text
IDLE
  → RUNNING_SIGNAL_DETECTION
  → RUNNING_EVIDENCE_SEARCH
  → RUNNING_HYPOTHESIS_GENERATION
  → RUNNING_EXPERIMENT_GENERATION
  → WAITING_FOR_APPROVAL
  → APPLYING_APPROVED_ACTIONS
  → GENERATING_BRIEF
  → COMPLETED

Error states:
  → FAILED_ELASTIC_SEARCH
  → FAILED_GEMINI_OUTPUT_VALIDATION
  → FAILED_ACTION_APPLICATION
```

---

## 9. Elastic Design

### 9.1 Elastic 역할

Elastic은 LaunchPilot의 **evidence engine**이다.

- 구조화 데이터 검색: follower_logs, content_posts, campaigns, calendar_events
- 비구조화 데이터 검색: team_notes, growth_briefs
- ES|QL 기반 집계: baseline, anomaly, channel comparison
- semantic/hybrid search: 팬 반응, 콘텐츠 문맥, 과거 리포트 검색
- MCP exposure: Google Cloud Agent Builder에서 Elastic tools 호출

### 9.2 Index list

| Index | 목적 |
|---|---|
| follower_logs | 채널별 팔로워 시계열 변화 계산 |
| content_posts | 콘텐츠 성과, 포맷, hook, CTA, 참여율 검색 |
| campaigns | 캠페인 목표, 단계, 기간, 타겟 지표 검색 |
| calendar_events | 업로드 일정, missed event, 일정 공백 검색 |
| team_notes | 팬 반응, 운영 메모, 외부 이벤트 검색 |
| growth_briefs | 과거 분석 결과와 실험 결과 검색 |

### 9.3 Index fields

#### follower_logs

| Field | Type | Description |
|---|---|---|
| id | keyword | unique id |
| creator_id | keyword | creator id |
| campaign_id | keyword | optional campaign id |
| channel | keyword | instagram/tiktok/youtube/x |
| follower_count | integer | follower count |
| recorded_at | date | snapshot date |
| source | keyword | seed/csv/manual/api |
| note | text | optional note |

Sample:

```json
{
  "id": "fl_20260601_tiktok",
  "creator_id": "creator_luna",
  "campaign_id": "camp_comeback_teaser",
  "channel": "tiktok",
  "follower_count": 128400,
  "recorded_at": "2026-06-01T09:00:00+09:00",
  "source": "seed",
  "note": "Spike started after BTS practice short"
}
```

#### content_posts

| Field | Type | Description |
|---|---|---|
| id | keyword | unique id |
| creator_id | keyword | creator id |
| campaign_id | keyword | related campaign |
| channel | keyword | platform |
| title | text | content title |
| content_type | keyword | reel/short/video/post/thread |
| content_angle | keyword | bts/teaser/challenge/fan_reply/tutorial/collab |
| hook_type | keyword | face_first/question/reveal/comment_reply/caption_first |
| cta_type | keyword | comment/save/follow/share/none |
| posted_at | date | published datetime |
| views | integer | view count |
| reach | integer | reach count |
| likes | integer | like count |
| comments | integer | comment count |
| saves | integer | save count |
| shares | integer | share count |
| engagement_rate | float | computed |
| save_rate | float | computed |
| comment_rate | float | computed |
| transcript | text | optional text/transcript |

#### campaigns

| Field | Type | Description |
|---|---|---|
| id | keyword | campaign id |
| creator_id | keyword | creator id |
| name | text | campaign name |
| phase | keyword | teaser/launch/followup/custom |
| objective | keyword | follower_growth/engagement/awareness/conversion |
| target_metric_key | keyword | follower_delta/save_rate/comment_rate/views |
| target_metric_value | float | numeric target |
| start_date | date | start date |
| end_date | date | end date |
| status | keyword | active/completed/planned |
| description | text | campaign context |

#### calendar_events

| Field | Type | Description |
|---|---|---|
| id | keyword | event id |
| campaign_id | keyword | campaign id |
| channel | keyword | platform |
| content_type | keyword | reel/short/video/post |
| scheduled_at | date | schedule datetime |
| status | keyword | scheduled/completed/missed |
| title | text | event title |
| experiment_id | keyword | optional experiment item id |

#### team_notes

| Field | Type | Description |
|---|---|---|
| id | keyword | note id |
| entity_type | keyword | post/campaign/calendar_event/general |
| entity_id | keyword | related entity |
| campaign_id | keyword | campaign id |
| created_at | date | created datetime |
| author_role | keyword | manager/creator/editor |
| body | text | note body |
| tags | keyword[] | fan_reaction/external_event/production_issue |

#### growth_briefs

| Field | Type | Description |
|---|---|---|
| id | keyword | brief id |
| campaign_id | keyword | campaign id |
| created_at | date | created datetime |
| summary | text | report summary |
| signals | object[] | included signals |
| hypotheses | object[] | included hypotheses |
| experiments | object[] | included experiment items |
| evidence_refs | keyword[] | evidence ids |

### 9.4 Query examples

#### 최근 30일 평균 대비 성과가 높은 콘텐츠 찾기

```esql
FROM content_posts
| WHERE posted_at >= NOW() - 30 DAYS
| EVAL save_rate = saves / CASE(reach == 0, 1, reach)
| STATS avg_save_rate = AVG(save_rate), avg_views = AVG(views) BY channel, content_angle
| SORT avg_save_rate DESC
| LIMIT 10
```

#### 성장 급등 구간과 같은 시간대의 콘텐츠 찾기

```esql
FROM content_posts
| WHERE posted_at >= DATE_PARSE("2026-06-01T00:00:00+09:00")
  AND posted_at <= DATE_PARSE("2026-06-03T23:59:59+09:00")
| KEEP id, title, channel, content_angle, hook_type, views, saves, comments, posted_at
| SORT views DESC
| LIMIT 10
```

#### missed upload과 성장 정체 구간 찾기

```esql
FROM calendar_events
| WHERE status == "missed" AND scheduled_at >= NOW() - 14 DAYS
| KEEP id, title, channel, scheduled_at, campaign_id
| SORT scheduled_at DESC
```

#### 팀 메모에서 팬 반응 문장 검색

Semantic/hybrid search query:

```json
{
  "index": "team_notes",
  "query": {
    "match": {
      "body": "fans reacted strongly to behind the scenes raw practice clip"
    }
  },
  "size": 5
}
```

---

## 10. Data Model

### 10.1 Entity relationships

```text
Creator 1 ── N Channel
Creator 1 ── N Campaign
Campaign 1 ── N ContentPost
Campaign 1 ── N CalendarEvent
Campaign 1 ── N TeamNote
Campaign 1 ── N GrowthSignal
GrowthSignal N ── N EvidenceRef
GrowthSignal 1 ── N Hypothesis
Hypothesis 1 ── N ExperimentItem
ExperimentPlan 1 ── N ExperimentItem
ExperimentPlan 1 ── 1 GrowthBrief
AgentRun 1 ── N AgentActionLog
```

### 10.2 Entity fields

#### Creator

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | string | yes | creator_luna |
| name | string | yes | display name |
| category | string | no | kpop/beauty/fitness/brand |
| timezone | string | yes | Asia/Seoul |

#### Channel

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | string | yes | channel id |
| creator_id | string | yes | FK |
| platform | enum | yes | instagram/tiktok/youtube/x |
| handle | string | yes | @handle |
| url | string | no | profile url |

#### FollowerLog

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| creator_id | string | yes |
| channel | enum | yes |
| follower_count | number | yes |
| recorded_at | datetime | yes |
| source | enum | yes |
| note | string | no |

#### ContentPost

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| creator_id | string | yes |
| campaign_id | string | no |
| channel | enum | yes |
| title | string | yes |
| posted_at | datetime | yes |
| content_type | enum | yes |
| content_angle | enum/string | yes |
| hook_type | enum/string | no |
| cta_type | enum/string | no |
| views | number | no |
| reach | number | no |
| likes | number | no |
| comments | number | no |
| saves | number | no |
| shares | number | no |
| transcript | string | no |

#### Campaign

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| creator_id | string | yes |
| name | string | yes |
| objective | enum | yes |
| phase | string | yes |
| start_date | date | yes |
| end_date | date | yes |
| target_metric_key | string | yes |
| target_metric_value | number | yes |
| status | enum | yes |

#### CalendarEvent

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| campaign_id | string | yes |
| title | string | yes |
| channel | enum | yes |
| content_type | enum | yes |
| scheduled_at | datetime | yes |
| status | enum | yes |
| experiment_item_id | string | no |

#### TeamNote

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| campaign_id | string | no |
| entity_type | enum | yes |
| entity_id | string | no |
| body | string | yes |
| tags | string[] | no |
| created_at | datetime | yes |

#### GrowthSignal

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| campaign_id | string | yes |
| type | enum | yes |
| title | string | yes |
| description | string | yes |
| metric_name | string | yes |
| current_value | number | yes |
| baseline_value | number | no |
| lift_ratio | number | no |
| date_window | object | yes |
| evidence_refs | string[] | yes |
| confidence | enum | yes |

#### Hypothesis

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| signal_id | string | yes |
| statement | string | yes |
| rationale | string | yes |
| supporting_evidence_refs | string[] | yes |
| confidence | enum | yes |
| caveats | string[] | yes |

#### ExperimentPlan

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| campaign_id | string | yes |
| status | enum | yes |
| created_at | datetime | yes |
| summary | string | yes |
| owner_note | string | no |

#### ExperimentItem

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| experiment_plan_id | string | yes |
| hypothesis_id | string | yes |
| title | string | yes |
| channel | enum | yes |
| content_format | string | yes |
| hook | string | yes |
| cta | string | yes |
| target_metric | string | yes |
| success_criteria | string | yes |
| scheduled_at | datetime | yes |
| production_brief | string | yes |

#### GrowthBrief

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| campaign_id | string | yes |
| experiment_plan_id | string | yes |
| title | string | yes |
| summary | string | yes |
| markdown | string | yes |
| created_at | datetime | yes |

#### AgentActionLog

| Field | Type | Required |
|---|---|---:|
| id | string | yes |
| agent_run_id | string | yes |
| tool_name | string | yes |
| input_json | json | yes |
| output_json | json | yes |
| status | enum | yes |
| started_at | datetime | yes |
| completed_at | datetime | no |
| error_message | string | no |

---

## 11. UI/UX Requirements

### 11.1 UI principle

UI는 “대시보드”가 아니라 **캠페인 의사결정 작업 공간**이어야 한다. 특정 화면명이 반드시 “War Room”일 필요는 없다. 중요한 것은 사용자가 차트를 구경하는 것이 아니라, 선택한 캠페인에서 근거를 확인하고 다음 실험안을 결정하는 흐름이다.

> “What should we test next week?”

의도 중심 요구:

- Campaigns는 사용자가 캠페인 단위 업무를 인지하고 시작하는 진입점이다.
- Experiment Planner는 선택된 캠페인 안에서 evidence-backed signal, hypothesis, experiment plan, approval을 다루는 작업 공간이다.
- Calendar와 Briefs는 승인 이후 생성된 산출물을 확인하는 영역이다.
- 진행 상태와 승인 상태는 작업 공간 내부에서 표현하고, 사이드 내비게이션은 전역 이동과 현재 캠페인 맥락만 유지한다.

### 11.2 Required screens

#### 1. Landing / Demo Entry

- 목적: 제품 가치와 demo 시작점을 명확히 제공.
- 주요 컴포넌트:
  - Hero: “Turn creator analytics into next-week experiments.”
  - CTA: “Launch demo planner”
  - Track badges: Gemini, Google Cloud Agent Builder, Elastic MCP
- Empty state: 없음.
- Error state: demo dataset 로딩 실패 시 reset CTA 표시.

#### 2. Data Import / Demo Dataset Selector

- 목적: seed data 또는 CSV import 선택.
- 주요 컴포넌트:
  - Dataset card: Comeback Teaser Campaign
  - Upload CSV button
  - Import status table
- 버튼:
  - Import seed dataset
  - Upload CSV
  - Reset demo

#### 3. Experiment Planner Workspace

3패널 구조.

| 영역 | 내용 |
|---|---|
| Left | Campaign timeline, metrics, follower trend, calendar density |
| Center | Agent findings, signal cards, evidence drawer |
| Right | Hypothesis, experiment plan, approval actions |

메인 CTA:

> **What should we test next week?**

#### 4. Signal Cards

각 카드 포함 항목:

- signal title
- channel
- metric
- baseline vs current
- lift ratio
- confidence
- evidence count
- “View evidence” button

#### 5. Evidence Drawer

- content posts
- team notes
- campaign phase
- calendar events
- previous growth brief excerpts
- tool call log

각 evidence에는 source, timestamp, metric, reason_for_relevance를 표시한다.

#### 6. Hypothesis Panel

- hypothesis statement
- rationale
- supporting evidence ids
- confidence
- caveats
- “Turn into experiment” relationship 표시

#### 7. Experiment Plan Panel

각 실험 item 표시:

- experiment title
- hypothesis tested
- channel
- hook
- CTA
- target metric
- success criteria
- scheduled date
- production brief

Buttons:

- Approve experiments
- Edit plan
- Reject plan

MVP에서는 Edit plan은 modal에서 text override만 허용해도 된다.

#### 8. Approval Modal

승인 전 확인 문구:

- 생성될 calendar events 수
- 생성될 Growth Brief 제목
- “No autonomous posting will happen” 문구
- Approve / Cancel

#### 9. Calendar View

- week view
- experiment items as scheduled cards
- status: planned/completed/missed
- linked hypothesis 표시

#### 10. Growth Brief View

- One-page summary
- top signals
- hypotheses
- experiments
- evidence appendix
- copy/share/export button

---

## 12. API / Backend Requirements

### 12.1 API list

| Method | Path | Purpose |
|---|---|---|
| POST | /api/import/seed | seed dataset import |
| POST | /api/import/csv | CSV upload/import |
| POST | /api/elastic/reindex | app DB → Elastic reindex |
| POST | /api/agent/run | LaunchPilot agent 실행 |
| GET | /api/agent/runs/:id | agent run status 조회 |
| POST | /api/agent/actions/:id/approve | pending plan 승인 |
| POST | /api/agent/actions/:id/reject | pending plan 거절 |
| GET | /api/calendar | calendar events 조회 |
| POST | /api/calendar/events | calendar event 생성 |
| GET | /api/growth-briefs/:id | Growth Brief 조회 |
| POST | /api/demo/reset | demo reset |

### 12.2 API examples

#### POST /api/import/seed

Request:

```json
{
  "dataset_id": "comeback_teaser_demo",
  "reset_existing": true
}
```

Response:

```json
{
  "ok": true,
  "workspace_id": "demo_workspace",
  "imported": {
    "creators": 1,
    "follower_logs": 60,
    "content_posts": 45,
    "campaigns": 1,
    "calendar_events": 18,
    "team_notes": 10
  },
  "elastic_indexing_status": "completed"
}
```

#### POST /api/agent/run

Request:

```json
{
  "workspace_id": "demo_workspace",
  "campaign_id": "camp_comeback_teaser",
  "question": "What should we test next week?",
  "date_range": {
    "start": "2026-05-25",
    "end": "2026-06-01"
  }
}
```

Response:

```json
{
  "agent_run_id": "run_001",
  "status": "running",
  "next_poll_url": "/api/agent/runs/run_001"
}
```

#### GET /api/agent/runs/:id

Response:

```json
{
  "agent_run_id": "run_001",
  "status": "waiting_for_approval",
  "signals": [],
  "hypotheses": [],
  "experiment_plan": {},
  "tool_call_logs": []
}
```

#### POST /api/agent/actions/:id/approve

Request:

```json
{
  "experiment_plan_id": "plan_001",
  "approved_by": "demo_user"
}
```

Response:

```json
{
  "ok": true,
  "created_calendar_events": ["cal_101", "cal_102", "cal_103"],
  "growth_brief_id": "brief_001"
}
```

---

## 13. AI Prompting & Output Schema

### 13.1 Gemini role

Gemini는 Elastic에서 검색된 evidence를 바탕으로 다음을 수행한다.

- signal 설명 문장 생성
- evidence 기반 hypothesis 작성
- experiment item 설계
- Growth Brief 작성

Gemini는 raw DB 전체를 추측하지 않는다. 반드시 tool output과 evidence_refs를 입력으로 받아야 한다.

### 13.2 System prompt 핵심 규칙

```text
You are LaunchPilot Agent, a growth signal interpreter for creator teams.
Your job is to turn social performance data into signals, hypotheses, and next-week content experiments.
Never claim causality. Use evidence-based and correlation-aware language.
Every hypothesis must include confidence, supporting evidence, and caveats.
Do not modify calendar or report data unless the user approves.
If evidence is insufficient, say insufficient_data.
Return strictly valid JSON following the provided schema.
```

### 13.3 Output schema

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
      "evidence_refs": ["post_014", "post_017", "note_006"]
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
  "experiments": [
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
  ],
  "recommended_actions": [
    {
      "type": "create_calendar_event",
      "experiment_id": "exp_001",
      "requires_approval": true
    }
  ],
  "report_summary": "This week’s strongest signal is not total TikTok growth alone, but repeated overperformance from BTS short-form clips. Next week should test whether the same raw format can reproduce engagement uplift across TikTok and Instagram.",
  "overall_confidence": "medium_high"
}
```

### 13.4 Validation rules

- signals.length >= 3 for demo dataset
- each signal.evidence_refs.length >= 2
- each hypothesis.caveats.length >= 1
- each experiment has target_metric and success_criteria
- no string may include “caused growth” or “because of this content” unless framed as hypothesis/correlation

---

## 14. Safety, Accuracy, and Trust

### 14.1 Required principles

| Principle | Product behavior |
|---|---|
| No causal overclaim | “caused” 대신 “associated with”, “linked to”, “candidate driver” 사용 |
| Evidence-first | 모든 signal/hypothesis에 evidence refs 표시 |
| Confidence 표시 | high / medium_high / medium / low |
| 데이터 부족 처리 | insufficient_data 상태를 명시 |
| Human approval | 승인 전 calendar/report 변경 금지 |
| Transparency | Evidence Drawer와 tool call log 제공 |
| Reproducibility | demo reset 후 동일한 흐름 재현 가능 |

### 14.2 Confidence rubric

| Confidence | 조건 |
|---|---|
| high | 동일 패턴의 콘텐츠 2개 이상, baseline 대비 2x 이상, 관련 메모/캘린더 근거 존재 |
| medium_high | 콘텐츠 성과와 시간 정렬이 강하나 외부 이벤트 근거 부족 |
| medium | signal은 있으나 반복성 또는 문맥 근거가 약함 |
| low | 데이터가 부족하거나 conflicting evidence 존재 |

### 14.3 Forbidden output examples

금지:

> “이 영상이 팔로워 증가를 만들었습니다.”

허용:

> “이 영상은 해당 성장 구간과 가장 강하게 연결된 원인 후보입니다. 같은 기간 성과 지표와 팀 메모를 함께 보면 BTS 포맷 가설을 다음 주에 검증할 가치가 있습니다.”

---

## 15. Hackathon Demo Scenario

### 15.1 3분 데모 목표

심사위원이 다음을 이해해야 한다.

1. LaunchPilot은 챗봇이 아니다.
2. Elastic MCP를 사용해 근거를 검색한다.
3. Gemini가 데이터를 해석해 가설과 실험안을 만든다.
4. 사용자가 승인하면 실제 캘린더와 보고서가 생성된다.

### 15.2 데모 스크립트

| 시간 | 화면 | 내레이션 |
|---|---|---|
| 0:00–0:20 | Landing | “Creator teams have analytics, but not interpretation. They still ask: what changed, why, and what should we test next?” |
| 0:20–0:40 | Dataset import | “We load a 60-day comeback campaign dataset: followers, posts, calendar events, notes, and past briefs.” |
| 0:40–1:00 | Experiment Planner | 사용자가 “What should we test next week?” 클릭 |
| 1:00–1:30 | Tool call log | “The agent queries Elastic through MCP: follower growth, content outperformance, campaign context, team notes, and missed calendar events.” |
| 1:30–1:55 | Signal Cards | “It finds three growth signals: BTS shorts overperformed, comment CTA lifted engagement, Instagram had missed uploads during flat growth.” |
| 1:55–2:20 | Hypothesis Panel | “Gemini turns evidence into cautious hypotheses, not causal claims.” |
| 2:20–2:40 | Experiment Plan | “The agent designs three next-week content experiments with target metrics and success criteria.” |
| 2:40–2:50 | Approval Modal | 사용자가 Approve experiments 클릭 |
| 2:50–3:00 | Calendar + Brief | “Approved experiments become calendar events and a client-ready Growth Brief. Built with Gemini, Google Cloud Agent Builder, and Elastic MCP.” |

---

## 16. Technical Architecture

### 16.1 Text diagram

```text
[Frontend: React / Next.js]
  ├─ Demo Dataset Selector
  ├─ Campaigns navigation
  ├─ Experiment Planner workspace
  ├─ Evidence Drawer
  ├─ Experiment Approval UI
  └─ Growth Brief View

        ↓ REST / tRPC

[Backend API: Node.js on Cloud Run]
  ├─ Import service
  ├─ Agent run service
  ├─ Calendar action service
  ├─ Growth brief service
  └─ Demo reset service

        ↓

[App Database: Postgres / Cloud SQL / SQLite for MVP]
  ├─ creators
  ├─ follower_logs
  ├─ content_posts
  ├─ campaigns
  ├─ calendar_events
  ├─ team_notes
  ├─ experiment_plans
  ├─ growth_briefs
  └─ agent_action_logs

        ↓ indexing

[Elastic Cloud Serverless]
  ├─ follower_logs index
  ├─ content_posts index
  ├─ campaigns index
  ├─ calendar_events index
  ├─ team_notes index
  └─ growth_briefs index

        ↕ MCP tools

[Google Cloud Agent Builder]
  ├─ LaunchPilot Agent
  ├─ Elastic MCP tools
  └─ Backend action tools

        ↓

[Gemini]
  ├─ signal explanation
  ├─ hypothesis generation
  ├─ experiment planning
  └─ growth brief drafting
```

### 16.2 Deployment target

- Frontend: Vercel 또는 Cloud Run static hosting
- Backend: Google Cloud Run
- App DB: Cloud SQL Postgres 또는 SQLite for demo simplicity
- Elastic: Elastic Cloud Serverless
- Agent: Google Cloud Agent Builder
- Model: Gemini

MVP에서는 안정성을 우선한다. DB/hosting 선택은 개발팀이 가장 빠르게 배포할 수 있는 조합으로 선택한다.

---

## 17. Milestones

### Day 1–2: Project setup and seed data

산출물:

- 새 GitHub repository
- README skeleton
- open-source license
- app skeleton
- seed dataset JSON/CSV
- demo reset script

완료 기준:

- `npm run dev` 또는 equivalent로 로컬 실행 가능
- seed import API가 최소 app DB에 데이터를 넣음

### Day 3–4: Elastic indexing and search tools

산출물:

- Elastic Cloud Serverless project
- index mappings
- bulk indexing script
- ES|QL queries
- semantic search tool definitions

완료 기준:

- Elastic에서 follower/content/team note 검색 가능
- 최소 4개 core query가 정상 작동

### Day 5–7: Agent orchestration

산출물:

- Google Cloud Agent Builder agent
- Elastic MCP 연결
- backend action tools
- Gemini structured output prompt
- agent action log 저장

완료 기준:

- “What should we test next week?” 실행 시 JSON result 생성
- signals/hypotheses/experiments가 UI에서 렌더링 가능한 형태로 반환

### Day 8–10: UI implementation

산출물:

- Experiment Planner 3패널 작업 공간
- Signal Cards
- Evidence Drawer
- Hypothesis Panel
- Experiment Plan Panel
- Approval Modal
- Calendar View
- Growth Brief View

완료 기준:

- demo flow가 클릭만으로 끝까지 진행됨

### Day 11–12: Demo polish

산출물:

- loading states
- error states
- tool call animation
- deterministic fallback result
- demo script

완료 기준:

- 네트워크/모델 지연 시에도 데모 실패하지 않음
- reset 후 3분 시나리오 재현 가능

### Day 13–14: Submission materials

산출물:

- hosted project URL
- public repo
- README with setup instructions
- 3-minute demo video
- Devpost description
- screenshots

완료 기준:

- 제3자가 README만 보고 실행 가능
- demo video가 3분 이내

---

## 18. Acceptance Criteria

### 18.1 Product acceptance

- 사용자는 seed dataset을 import할 수 있다.
- import 후 Elastic index에 데이터가 들어간다.
- 사용자는 “What should we test next week?”를 실행할 수 있다.
- agent run은 최소 3개의 signal을 생성한다.
- 각 signal에는 evidence reference가 최소 2개 존재한다.
- 각 hypothesis는 confidence와 caveat를 포함한다.
- experiment plan에는 최소 3개의 experiment item이 포함된다.
- 각 experiment item에는 target metric과 success criteria가 있다.
- 사용자 승인 전에는 calendar event가 생성되지 않는다.
- 승인 후 calendar event가 생성된다.
- 승인 후 Growth Brief가 생성된다.
- Evidence Drawer에서 signal/hypothesis의 근거를 확인할 수 있다.
- Demo Reset이 가능하다.

### 18.2 Technical acceptance

- Elastic MCP 또는 Elastic tool integration을 통해 Agent Builder가 검색 도구를 호출한다.
- Gemini 출력은 JSON schema validation을 통과한다.
- 실패 시 deterministic fallback을 제공한다.
- public repo에 setup instruction과 license가 포함된다.
- hosted web app이 접근 가능하다.

### 18.3 Demo acceptance

- 3분 안에 problem → agent run → evidence → experiments → approval → calendar/report flow가 보인다.
- 심사위원이 Elastic, Gemini, Google Cloud Agent Builder의 역할을 이해할 수 있다.
- 제품이 단순 챗봇이나 대시보드로 보이지 않는다.

---

## 19. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Elastic MCP 연동 실패 | agent가 partner MCP를 못 쓰는 것으로 보임 | Elastic search API fallback을 backend tool로 두되, MCP 연결 화면/로그를 우선 구현 |
| Gemini output instability | UI 파싱 실패 | JSON schema validation, retry, deterministic fallback sample result 제공 |
| seed data가 인위적으로 보임 | 실무성 약화 | noise, mixed signals, missed uploads, conflicting evidence를 포함해 현실감 부여 |
| demo latency | 3분 데모 실패 | precomputed result cache, skeleton loading, demo mode toggle |
| 기존 프로젝트 확장으로 오해 | 규칙 리스크 | 새 repo, 새 앱명, 새 UI, 새 dataset, 기존 운영 DB 미사용 |
| causal attribution 과장 | 신뢰도 하락 | “candidate driver”, “associated with”, “hypothesis” wording 강제 |
| UI가 대시보드처럼 보임 | 에이전트성 약화 | 중심 CTA를 “What should we test next week?”로 유지, signal/hypothesis/experiment decision flow를 중앙 작업 공간에 배치 |
| 범위 과다 | 완성도 하락 | API 연동, billing, multi workspace, autonomous posting 제외 |
| Elastic query 정확도 부족 | 근거 품질 저하 | seed data에 명확한 tags/hook/content_angle 필드 포함 |
| 사용자가 실험안을 신뢰하지 않음 | 실무성 저하 | evidence drawer, confidence, caveat 표시 |

---

## 20. Open Questions

개발 전 결정해야 할 질문.

1. App DB는 Postgres/Cloud SQL로 갈 것인가, SQLite/JSON file로 MVP를 단순화할 것인가?
2. Google Cloud Agent Builder에서 backend action tools를 어떻게 노출할 것인가?
3. Elastic MCP 연결이 지연될 경우 fallback architecture를 어디까지 허용할 것인가?
4. CSV import는 follower_logs/content_posts만 지원할 것인가, team_notes까지 지원할 것인가?
5. 데모용 seed campaign은 K-pop comeback으로 고정할 것인가, 범용 creator campaign으로 바꿀 것인가?
6. Experiment item의 edit 기능을 MVP에 포함할 것인가?
7. Growth Brief export는 markdown copy까지만 할 것인가, PDF까지 할 것인가?
8. demo video에서 technical log를 얼마나 보여줄 것인가?
9. confidence score는 rule-based로 계산할 것인가, Gemini가 제안하고 backend가 검증할 것인가?
10. 제출 repo에서 기존 PRD/서비스와의 관계를 어떻게 설명할 것인가?

---

## Appendix A. Demo seed data design

### A.1 Campaign

- Name: Luna Comeback Teaser Campaign
- Objective: follower_growth + engagement
- Phase: teaser
- Date range: 2026-05-01 to 2026-06-07
- Primary metric: follower_delta
- Secondary metrics: save_rate, comment_rate

### A.2 Intended hidden pattern

1. BTS/raw practice clips perform better than polished teaser assets.
2. Comment CTA increases comments but not always follower growth.
3. Instagram missed uploads correlate with flat growth.
4. YouTube Shorts shows delayed lift 24–48 hours after TikTok spike.

### A.3 Agent expected output

Signals:

- TikTok BTS shorts save rate 2.8x baseline
- Comment CTA posts comment rate 1.9x baseline
- Instagram missed two scheduled reels during flat growth

Hypotheses:

- Raw BTS format may be a repeatable engagement driver.
- Comment CTA may increase community interaction more than immediate follower conversion.
- Instagram stagnation may be more related to calendar consistency than creative quality.

Experiments:

- TikTok BTS face-first hook test
- Instagram repurposed BTS reel test
- Fan comment reply format test

---

## Appendix B. Developer implementation order

P0:

1. Seed import
2. Elastic indexing
3. Static signal detection
4. Gemini structured generation
5. Experiment Planner UI
6. Approval → calendar/report creation
7. Demo reset

P1:

1. CSV import
2. Evidence drawer polish
3. Tool call log
4. Growth Brief markdown export

P2:

1. Slack webhook
2. PDF export
3. Editable experiment plan
4. Multi-creator workspace
