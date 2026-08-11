# LaunchPilot Rebuild

LaunchPilot은 광고·콘텐츠 성과 데이터를 근거로 **신호를 찾고, 가설을 세우며, 다음 실험을 제안하는 마케팅 분석 에이전트**다.

현재 저장소는 Google ADK 해커톤 프로토타입을 그대로 확장하지 않는다. 같은 제품 문제를 유지하되, LangGraph 중심의 에이전트 설계와 평가 주도 개발을 경험하고 설명할 수 있는 포트폴리오 프로젝트로 새로 설계한다.

## Current status

| 항목 | 상태 |
| --- | --- |
| Phase 0 — Product & Evaluation Charter | 확정 |
| Phase 1 — Domain, Data & Evidence Design | 완료 |
| Phase 2 — Identity, Platform Connection & Data Ingestion | 내부 E2E 완료 · 실제 광고 계정 검증 대기 |
| Phase 3A — Structured Retrieval + BM25 Baseline | 완료 |
| Phase 4A — Retrieval Eval v1 | LangSmith 수신 검증 완료 · Golden Dataset 진행 중 |
| 신규 구현 | `services/launchpilot-api` |
| 해커톤 프로토타입 | `archive/`에 격리된 참고 자료 |
| 프로덕션 운영 인프라 | 포트폴리오 범위에서 제외 |

전체 로드맵과 문서 지도는 [`docs/README.md`](docs/README.md)를 단일 진입점으로 사용한다.

## Archived prototype

기존 문서와 구현은 당시 판단과 학습 과정을 보존하기 위한 자료다. 신규 설계의 현행 계약으로 사용하지 않는다.

- 전체 안내: [`archive/README.md`](archive/README.md)
- Google ADK 해커톤 구현과 문서: [`archive/google-adk-hackathon-prototype/`](archive/google-adk-hackathon-prototype/)
- 현재 리빌드 전에 대체된 설계: [`archive/superseded-designs/`](archive/superseded-designs/)

아카이브는 현행 빌드·테스트·배포 대상이 아니다. 현재 구현은 `services/`, 현재 결정은 [`docs/README.md`](docs/README.md)에서 연결하는 문서만 기준으로 한다.
