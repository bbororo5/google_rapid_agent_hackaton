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

현재 Retrieval Eval 작업의 구현 상태와 후속 PR 문안은
[Marketing Retrieval Evaluation 인수인계](rebuild/handoff-marketing-retrieval-evaluation.md)에
정리되어 있다.

## Current roadmap

| Phase | 상태 | 결과 또는 다음 결정 |
| --- | --- | --- |
| 0. Product & Evaluation Charter | 완료 | 사용자·권한·품질 기준 확정 |
| 1. Domain, Data & Evidence | 완료 | Campaign·Observation·Evidence 경계 확정 |
| 2. Identity & Data Ingestion | mock E2E 완료 | 실제 Ads 계정 검증 대기 |
| 3A. Retrieval Baseline | 완료 | PostgreSQL Structured Retrieval + Elasticsearch BM25 |
| 4A. Retrieval Eval v1 | 기술 완료·검수 대기 | Golden 600건과 문서 span 130건 생성 |
| 3B. Retrieval 고도화 | v1 완료 | 7 Chunker × 10 Retriever, 70조합 실행 |
| 4B. 비교 Eval | v1 완료 | validation 선택과 blind holdout 확인 |
| 5. Integrated Quality Optimization | 대기 | 검색·도구 선택·답변 품질 통합 개선 |
| 6. Portfolio Packaging | 대기 | 데모·아키텍처·면접 방어 자료 |

작업 순서는 `3A → 4A → 3B → 4B`다. 구현과 평가를 분리해 기술을 먼저 채택하고 근거를 나중에 붙이는 일을 막는다.

## Decisions

- [ADR-0001 — Elasticsearch를 검색 Projection 후보로 시험 채택](rebuild/adr/0001-retrieval-storage-strategy.md)
- [ADR-0002 — PostgreSQL을 Source of Truth로 채택](rebuild/adr/0002-source-of-truth-database.md)
- [ADR-0003 — 기능 중심 모듈러 모놀리스로 재구성](rebuild/adr/0003-feature-oriented-modular-monolith.md)
- [ADR-0004 — 마케팅 도메인 청킹 전략 (Whole Document & Fixed 400)](rebuild/adr/0004-chunking-strategy.md)
- [ADR-0005 — 초저지연 마케팅 도메인 피처 리랭킹 전략 (MarketingDomainReranker)](rebuild/adr/0005-reranking-strategy.md)
- [ADR-0006 — 결정론적 스코프 주입 및 조건부 라우팅 전략 (RouterNode)](rebuild/adr/0006-routing-strategy.md)

## Document rules

- Phase 문서는 제품·설계의 **무엇과 왜**, ADR은 대안이 있었던 기술 결정을 기록한다.
- 설치·환경변수·명령은 서비스 README, Dataset 규칙은 Dataset 옆에 둔다.
- 상태는 이 문서와 해당 Phase 문서에서만 갱신한다.
- 폐기된 문서는 [`archive/`](../archive/)로 이동하며 현행 읽기 경로에 섞지 않는다.
