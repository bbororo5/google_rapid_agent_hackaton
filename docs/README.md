# LaunchPilot Documentation

이 문서는 LaunchPilot 리빌드 문서의 단일 진입점이다. 제품·설계 결정은 `docs/rebuild/`, 실행 방법은 서비스 README, Eval 작성 방법은 서비스의 `evals/`에서 관리한다. 아카이브는 현행 결정의 근거로 사용하지 않는다.

## 현재 위치

| 구간 | 상태 | 다음 결정 |
| --- | --- | --- |
| Phase 0 — Product & Evaluation Charter | 완료 | — |
| Phase 1 — Domain, Data & Evidence Design | 완료 | — |
| Phase 2 — Identity & Data Ingestion | mock E2E 완료 | 실제 광고 계정 성과 검증 |
| Phase 3A — Retrieval Baseline | 완료 | Whole Document BM25 기준 점수 측정 |
| Phase 4A — Retrieval Eval v1 | 진행 중 | 협업 검수 Golden Dataset v1 확정 |
| Phase 3B — Retrieval 고도화 | 대기 | Chunking부터 한 요소씩 실험 |
| Phase 4B — Retrieval 비교 Eval | 대기 | 개선된 구성만 채택 |
| Phase 5 — Integrated Quality Optimization | 대기 | 검색·도구 선택·답변 품질 통합 개선 |
| Phase 6 — Portfolio Packaging | 대기 | 데모·아키텍처·면접 방어 자료 |

Phase 3A와 4A를 완료한 뒤 3B와 4B를 반복한다. 번호는 구현과 평가가 서로 다른 책임임을 나타내며, 실제 작업 순서는 `3A → 4A → 3B → 4B`다.

## 문서 지도

### 제품과 설계 — 무엇을 왜 만드는가

| 문서 | 답하는 질문 |
| --- | --- |
| [Phase 0 — Product & Evaluation Charter](rebuild/phase-0-decision-charter.md) | 누구의 어떤 문제를 어떤 품질과 권한으로 해결하는가? |
| [Phase 1 — Domain Model](rebuild/phase-1-domain-model.md) | 캠페인·관찰·근거·가설을 어떤 개념으로 표현하는가? |
| [Phase 2 — Multi-platform Ingestion](rebuild/phase-2-multiplatform-ingestion.md) | 플랫폼을 어떻게 연결하고 일관된 Observation으로 수집하는가? |
| [Retrieval Evolution Plan](rebuild/retrieval-evolution-plan.md) | Baseline을 어떤 Eval로 검증하고 어떻게 확장하는가? |
| [현행 설계 인덱스](rebuild/README.md) | 문서 상태와 ADR 목록은 무엇인가? |

### 기술 결정 — 왜 이 선택을 했는가

| ADR | 상태 |
| --- | --- |
| [ADR-0001 — Elasticsearch Retrieval 저장소](rebuild/adr/0001-retrieval-storage-strategy.md) | 시험 채택, Eval로 최종 판단 |
| [ADR-0002 — PostgreSQL Source of Truth](rebuild/adr/0002-source-of-truth-database.md) | 채택·구현 완료 |

### 구현과 검증 — 어떻게 실행하고 확인하는가

| 문서 | 범위 |
| --- | --- |
| [LaunchPilot API README](../services/launchpilot-api/README.md) | 로컬 실행, OAuth, mock, Retrieval, 테스트 |
| [Golden Dataset v1 안내](../services/launchpilot-api/evals/README.md) | Eval 사례 작성과 Ground Truth 규칙 |

### 과거 자료

[Archive 안내](../archive/README.md)는 Google ADK 해커톤 프로토타입과 폐기된 설계를 설명한다. 현재 구현이나 의사결정과 충돌하면 현행 문서가 우선한다.

## 문서 배치 규칙

- 제품 범위, 도메인, 로드맵처럼 **무엇과 왜**를 설명하면 `docs/rebuild/`에 둔다.
- 되돌리기 어렵거나 대안을 비교한 기술 선택은 `docs/rebuild/adr/`에 ADR로 남긴다.
- 설치·환경변수·실행·테스트처럼 코드와 함께 바뀌는 **어떻게**는 해당 서비스 README에 둔다.
- Dataset 작성 규칙과 실행 명령은 Dataset 가까이에 둔다.
- 더 이상 유효하지 않은 문서는 삭제하지 않고 `archive/`로 이동하며 현행 문서에서 연결하지 않는다.
- 진행 상태는 이 문서와 해당 Phase 문서에서만 갱신한다. 루트 README에는 세부 로드맵을 복제하지 않는다.
