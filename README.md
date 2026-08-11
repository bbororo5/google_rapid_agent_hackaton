# LaunchPilot Rebuild

LaunchPilot은 Google Ads·Meta Ads·YouTube 성과와 내부 문서 근거를 함께 분석해 다음 실험을 제안하는 마케팅 Agentic RAG 프로젝트다.

Google ADK 해커톤 프로토타입을 운영 전환하지 않고, 같은 제품 문제를 Python·FastAPI·LangGraph와 평가 주도 Retrieval로 다시 설계한다. 포트폴리오의 핵심은 프레임워크 사용 자체가 아니라 **근거 있는 기술 선택과 Eval을 통한 품질 개선 과정**이다.

## Start here

1. [문서 포털](docs/README.md)에서 현재 단계와 설계 흐름을 읽는다.
2. [LaunchPilot API](services/launchpilot-api/README.md)를 실행한다.
3. [Golden Dataset 안내](services/launchpilot-api/evals/README.md)에 따라 Eval 사례를 작성한다.

## Repository

| 경로 | 역할 |
| --- | --- |
| `docs/rebuild/` | 현행 제품·도메인·Retrieval 결정 |
| `services/launchpilot-api/` | 신규 FastAPI·LangGraph 구현 |
| `archive/` | Google ADK 프로토타입과 폐기된 설계; 현행 기준 아님 |

현재 결정과 구현이 아카이브와 충돌하면 [문서 포털](docs/README.md)을 우선한다.
