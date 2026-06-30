# [ADR-0016] Gemini 대체 로컬 LLM 검토

- **상태(Status):** 제안됨(Proposed)
- **날짜(Date):** 2026년 6월 30일
- **컨텍스트:** Google ADK Python 2.x, Docker Compose, macOS 16GB, Windows 16GB, Phoenix/Arize, 로컬 LLM

## 1. 맥락

GCP 예산 초과로 배포 리소스를 모두 내렸다. 당분간 개발과 검증은 로컬에서 가능해야 한다.

현재 로컬 Compose는 frontend, Java backend, Python agent, Elasticsearch, Redis를 실행한다. Phoenix/Arize는 무료 외부 서비스로 유지한다. 남은 외부 의존성은 LLM이다.

팀 환경은 macOS Apple Silicon 16GB와 Windows 16GB를 모두 포함한다. 로컬 LLM은 개인 장비의 최대 성능보다 팀 공통 실행 가능성을 우선한다.

## 2. 요구사항과 제약

- GCP 없이 agent workflow를 로컬에서 실행할 수 있어야 한다.
- Gemini/Vertex 경로는 제거하지 않는다. 배포 복구와 품질 비교 기준으로 남긴다.
- Phoenix/Arize 외부 연동은 유지한다.
- 기존 ADK `LlmAgent` worker 구조를 가능한 한 유지한다.
- Compose stack과 LLM이 16GB RAM 안에서 함께 실행되어야 한다.
- Windows는 GPU, WSL2, Docker Desktop 설정에 따라 성능 차이가 크다.
- 로컬 모델의 structured output과 tool 사용 안정성은 검증 전까지 확정할 수 없다.

## 3. 선택지

### A. Gemini/Vertex만 유지

구현 변경은 적지만 GCP 없는 로컬 실행 요구를 만족하지 못한다. 기본 개발 경로로는 제외한다.

### B. Host-managed local LLM runtime

Ollama, LM Studio, llama.cpp server 같은 runtime을 개발자 PC에 설치한다. agent 컨테이너는 호스트의 local LLM endpoint를 호출한다. ADK 통합은 LiteLLM connector 또는 model factory로 검증한다.

Compose는 앱과 데이터 인프라만 관리한다. macOS와 Windows 모두 같은 구조를 공유할 수 있어 1차 선택지로 둔다.

### C. Compose-managed LLM runtime

LLM runtime까지 Compose에 넣는다. 재현성은 좋아 보이지만 16GB 환경에서 메모리 부담이 크고, macOS에서는 GPU/Metal 활용이 불리할 수 있다. 기본 경로에서 제외한다.

### D. OS별 direct runtime

macOS는 MLX/LiteRT-LM, Windows는 별도 runtime을 직접 연동한다. 성능 최적화 여지는 있지만 OS별 코드와 절차가 갈라진다. 후순위로 둔다.

## 4. 모델 후보

모델은 런타임과 분리해 실험한다.

- 1차 후보: Gemma 4 E2B/E4B
- 비교 후보: Qwen 3 4B급, Llama 3.x 소형, Phi mini급
- 제외: 12B 이상 모델은 16GB 팀 기본 환경의 기본 후보에서 제외한다.

## 5. 트레이드오프

| 선택지 | GCP 없이 실행 | 16GB 팀 환경 | 구현 부담 | 판단 |
|---|---:|---:|---:|---|
| Gemini/Vertex만 유지 | 불가 | 좋음 | 낮음 | 제외 |
| Host-managed local runtime | 가능 | 가장 현실적 | 중간 | 채택 후보 |
| Compose-managed LLM runtime | 가능 | 부담 큼 | 중간 | 제외 |
| OS별 direct runtime | 가능 | 불확실 | 높음 | 후순위 |

## 6. 결정

Gemini 대체재로 로컬 LLM 경로를 추가한다.

- 기본 방향은 host-managed local LLM runtime으로 한다.
- LLM runtime은 Docker Compose에 포함하지 않는다.
- Compose는 frontend, backend, agent, Elasticsearch, Redis까지만 관리한다.
- 기존 Gemini/Vertex 경로는 유지한다.
- Phoenix/Arize 외부 연동은 유지한다.
- 1차 runtime 후보는 Ollama로 둔다.
- 1차 모델 후보는 Gemma 4 E2B/E4B로 둔다.
- Qwen, Llama, Phi 소형 모델을 비교 후보로 둔다.

## 7. 결과

GCP 없이도 agent workflow를 로컬 LLM으로 개발·검증할 수 있는 경로가 생긴다. 대신 개발자는 로컬 LLM runtime 설치와 모델 다운로드를 별도로 수행해야 한다.

local model과 cloud Gemini는 출력 품질과 structured output 안정성이 다를 수 있다. 테스트와 평가에서는 cloud path와 local path를 구분한다.

## 8. 후속 작업

- ADK 2.x에서 LiteLLM/Ollama 통합을 검증한다.
- agent에 LLM provider/model factory를 추가한다.
- `.env.example`과 README에 local LLM 설정을 추가한다.
- Gemma 4 E2B/E4B와 비교 후보의 smoke test 결과를 이 ADR에 업데이트한다.
