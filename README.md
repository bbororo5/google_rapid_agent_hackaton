# LaunchPilot Rebuild

LaunchPilot은 광고·콘텐츠 성과 데이터를 근거로 **신호를 찾고, 가설을 세우며, 다음 실험을 제안하는 마케팅 분석 에이전트**다.

현재 저장소는 Google ADK 해커톤 프로토타입을 그대로 확장하지 않는다. 같은 제품 문제를 유지하되, LangGraph 중심의 에이전트 설계와 평가 주도 개발을 경험하고 설명할 수 있는 포트폴리오 프로젝트로 새로 설계한다.

## Current status

| 항목 | 상태 |
| --- | --- |
| Phase 0 — Product & Evaluation Charter | 확정 |
| Phase 1 — Domain, Data & Evidence Design | **현재 단계** · 핵심 모델과 FastAPI vertical slice 구현 |
| Phase 2 — Identity, Platform Connection & Data Ingestion | Google 로그인 · YouTube 요청 기반 수집 경로 선행 구현 |
| 신규 구현 | `services/launchpilot-api` |
| 해커톤 프로토타입 | 아카이브·참고 자료 |
| 프로덕션 운영 인프라 | 포트폴리오 범위에서 제외 |

현재 문서 인덱스: [`docs/rebuild/README.md`](docs/rebuild/README.md)

## Roadmap

1. **Phase 0 — Product & Evaluation Charter:** 제품 문제, 에이전트 권한, 품질 기준 확정
2. **Phase 1 — Domain, Data & Evidence Design:** 도메인 모델과 근거 구조 설계
3. **Phase 2 — Identity, Platform Connection & Data Ingestion:** 로그인, OAuth 연결, 사용자 요청 기반 데이터 수집
4. **Phase 3 — Retrieval Baseline:** 구조화 조회와 기본 검색 구현
5. **Phase 4 — Eval v1:** 대표 질문·기대 근거·최초 기준 점수 구축
6. **Phase 5 — LangGraph Agent Runtime:** 상태 기반 에이전트 런타임 구현
7. **Phase 6 — Advanced Retrieval & Eval:** 하이브리드·그래프 검색 비교 실험
8. **Phase 7 — Integrated Quality Optimization:** 검색·도구 선택·답변 품질 통합 최적화
9. **Phase 8 — Portfolio Packaging:** 데모와 기술면접 방어 자료 정리

## Archived prototype

기존 문서와 구현은 당시 판단과 학습 과정을 보존하기 위한 자료다. 신규 설계의 현행 계약으로 사용하지 않는다.

- 문서: [`docs/archive/`](docs/archive/README.md)
- 구현: `apps/`, `backend/`, `contracts/`, `e2e/`, `fixtures/`, `mock/`, `observability/`, `scenarios/`, `tools/`

각 구현 영역의 `ARCHIVED.md`에 상태와 사용 원칙을 표시했다.
