# LaunchPilot Documentation

이 문서는 현행 설계의 단일 진입점이다. 아래 순서대로 읽으면 제품 문제에서 현재 Eval 작업까지 이어진다.

## Reading path

| 순서 | 문서 | 읽고 나면 답할 수 있는 질문 |
| --- | --- | --- |
| 1 | [Phase 0 — Product & Evaluation Charter](rebuild/phase-0-decision-charter.md) | 누구의 어떤 결정을 에이전트가 어떤 권한과 품질로 돕는가? |
| 2 | [Phase 1 — Domain Model](rebuild/phase-1-domain-model.md) | 플랫폼 데이터와 관측 사실·LLM 산출물을 어떻게 구분하는가? |
| 3 | [Phase 2 — Multi-platform Ingestion](rebuild/phase-2-multiplatform-ingestion.md) | 외부 계정과 Campaign을 어떻게 연결하고 수집하는가? |
| 4 | [Retrieval Evolution Plan](rebuild/retrieval-evolution-plan.md) | Baseline을 무엇으로 측정하고 어떤 순서로 개선하는가? |

필요한 기술 선택의 상세 근거는 해당 Phase에서 ADR로 연결한다. 실행 방법은 [API README](../services/launchpilot-api/README.md), Dataset 작성법은 [Eval README](../services/launchpilot-api/evals/README.md)에만 둔다.

## Current roadmap

| Phase | 상태 | 결과 또는 다음 결정 |
| --- | --- | --- |
| 0. Product & Evaluation Charter | 완료 | 사용자·권한·품질 기준 확정 |
| 1. Domain, Data & Evidence | 완료 | Campaign·Observation·Evidence 경계 확정 |
| 2. Identity & Data Ingestion | mock E2E 완료 | 실제 Ads 계정 검증 대기 |
| 3A. Retrieval Baseline | 완료 | PostgreSQL Structured Retrieval + Elasticsearch BM25 |
| 4A. Retrieval Eval v1 | 진행 중 | Golden Dataset 협업 검수와 기준 점수 |
| 3B. Retrieval 고도화 | 대기 | Chunking부터 한 요소씩 실험 |
| 4B. 비교 Eval | 대기 | 같은 Dataset에서 개선된 구성만 채택 |
| 5. Integrated Quality Optimization | 대기 | 검색·도구 선택·답변 품질 통합 개선 |
| 6. Portfolio Packaging | 대기 | 데모·아키텍처·면접 방어 자료 |

작업 순서는 `3A → 4A → 3B → 4B`다. 구현과 평가를 분리해 기술을 먼저 채택하고 근거를 나중에 붙이는 일을 막는다.

## Decisions

- [ADR-0001 — Elasticsearch를 검색 Projection 후보로 시험 채택](rebuild/adr/0001-retrieval-storage-strategy.md)
- [ADR-0002 — PostgreSQL을 Source of Truth로 채택](rebuild/adr/0002-source-of-truth-database.md)
- [ADR-0003 — 기능 중심 모듈러 모놀리스로 재구성](rebuild/adr/0003-feature-oriented-modular-monolith.md)

## Document rules

- Phase 문서는 제품·설계의 **무엇과 왜**, ADR은 대안이 있었던 기술 결정을 기록한다.
- 설치·환경변수·명령은 서비스 README, Dataset 규칙은 Dataset 옆에 둔다.
- 상태는 이 문서와 해당 Phase 문서에서만 갱신한다.
- 폐기된 문서는 [`archive/`](../archive/)로 이동하며 현행 읽기 경로에 섞지 않는다.
