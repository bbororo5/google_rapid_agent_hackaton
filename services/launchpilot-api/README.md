# LaunchPilot API

FastAPI 기반 Agentic RAG 서비스다. PostgreSQL Structured Retrieval, Elasticsearch BM25와 최소 LangGraph tool loop를 제공한다. 제품·설계는 [문서 포털](../../docs/README.md), Dataset 규칙은 [Eval README](evals/README.md)를 먼저 본다.

## Package boundaries

코드는 기술 계층보다 제품 기능을 기준으로 찾는다.

| 패키지 | 책임 |
| --- | --- |
| `identity` | 로그인, Workspace, 플랫폼 권한 |
| `campaigns` | Campaign, Conversation, 외부 Campaign 연결 |
| `performance` | 성과 수집, Observation, 정형 조회 |
| `knowledge` | 문서 원본, BM25 검색 |
| `analysis` | LangGraph, Tool, Evidence, 답변 생성 |
| `evaluation` | Golden Dataset과 Eval |
| `bootstrap` | 설정, 객체 조립, FastAPI 실행 |
| `observability` | OpenTelemetry/OpenInference 계측 |
| `persistence`, `shared`, `devtools` | 공유 실행 기반과 개발 지원 |

기능 내부는 `전문 Contract → use case → domain/port → adapter` 방향을 따른다. 예를 들어 `campaigns/contracts/access.py`는 Campaign 권한 범위를, `performance/contracts/retrieval.py`는 정형 검색 메시지를, `knowledge/contracts/retrieval.py`는 문서 검색 메시지를 정의한다. `public.py` 같은 포괄적 export는 사용하지 않으며 다른 기능은 상대 기능의 `contracts/<책임>.py`만 참조한다.

PostgreSQL·Elasticsearch·외부 API 구현은 Port 뒤에 두고 `bootstrap/wiring.py`에서 조립한다. 이 규칙은 `tests/test_architecture.py`가 검사하며, 결정 배경은 [ADR-0003](../../docs/rebuild/adr/0003-feature-oriented-modular-monolith.md)에 있다.

내부 컴포넌트도 구체 서비스가 아닌 필요한 역할을 생성자로 받는다. `tests/test_component_collaboration.py`는 주요 컴포넌트가 `CampaignReader`, `ObservationRecorder`, `AccessTokenProvider` 같은 역할 인터페이스로 연결되는지 검사한다.

## Quick start

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
docker compose up -d postgres elasticsearch
cp .env.example .env
.venv/bin/uvicorn launchpilot.main:app --reload --env-file .env
```

OpenAPI: `http://127.0.0.1:8000/docs`

Gemini는 `.env.example`의 Vertex AI + ADC 구성을 권장한다. 로컬에서 `gcloud auth application-default login`을 실행하거나 Google AI Studio의 `GOOGLE_API_KEY`를 사용한다.

## Required configuration

### Application secrets

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

첫 값은 `APP_SESSION_SECRET`, 둘째 값은 `TOKEN_ENCRYPTION_KEY`다. 플랫폼 Secret과 재사용하지 않으며 `.env`는 커밋하지 않는다.

### Platform setup

| 플랫폼 | 필요한 설정 | Callback |
| --- | --- | --- |
| Google 로그인 | OAuth Client, test user | `/auth/google/callback` |
| YouTube | Data API v3, Analytics API | `/connections/youtube/callback` |
| Google Ads | Ads API, Developer Token, `adwords` scope | `/connections/google-ads/callback` |
| Meta Ads | Meta 앱, Marketing API, `ads_read` | `/connections/meta-ads/callback` |

Callback 앞에는 `PUBLIC_BASE_URL`을 붙인다. HTTPS 환경은 실제 도메인과 `COOKIE_SECURE=true`를 사용한다. 개발 모드의 Meta 사용자는 앱 역할과 테스트할 광고 자산에 접근할 수 있어야 한다.

## Core flow

```text
GET  /auth/google/login
GET  /connections/{provider}/authorize
GET  /connections/{connection_id}/accounts
GET  /connections/{connection_id}/campaigns?account_ref=...
POST /campaigns/{campaign_id}/bindings
POST /campaigns/{campaign_id}/observations/ads
POST /campaigns/{campaign_id}/documents
POST /campaigns/{campaign_id}/analysis
```

로그인 후 플랫폼 읽기 권한을 연결하고 외부 Campaign을 LaunchPilot Campaign에 binding한다. 분석 시 광고 데이터를 수집해 PostgreSQL Observation으로 저장하고, Agent가 Structured Retrieval과 BM25 문서 검색을 선택한다.

- 일부 플랫폼 실패: 성공한 Slice와 실패 사유를 `PARTIAL`로 저장
- 전체 실패: 빈 Observation을 만들지 않음
- 문서 원본: PostgreSQL; Elasticsearch는 재생성 가능한 검색 Projection
- 검색 근거: BM25 hit를 PostgreSQL 원문으로 resolve한 뒤 사용
- Tool scope: Workspace·Campaign 범위를 서버가 주입

Projection 재생성: `POST /campaigns/{campaign_id}/documents/reindex`

## Observability

OpenInference가 LangChain/LangGraph를, OpenTelemetry가 FastAPI·HTTPX·PostgreSQL을 계측해 하나의 OTLP exporter로 LangSmith에 전송한다.

```env
TELEMETRY_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.smith.langchain.com/otel
OTEL_EXPORTER_OTLP_HEADERS=x-api-key=YOUR_KEY,Langsmith-Project=launchpilot-eval-v1
```

APAC endpoint는 `https://apac.api.smith.langchain.com/otel`이다. LangSmith 네이티브 tracing은 중복 활성화하지 않는다.

## Local platform mock

실제 광고 Campaign 없이 Google Ads·Meta Ads·YouTube가 하나의 `LunchPilot 여름 신규고객 캠페인`을 나타내는 E2E 흐름을 검증한다.

```bash
# terminal 1
.venv/bin/uvicorn launchpilot.devtools.mock_platforms.main:app --port 9000

# terminal 2
cp .env.mock.example .env.mock
.venv/bin/uvicorn launchpilot.main:app --reload --env-file .env.mock
```

- Mock OpenAPI: `http://127.0.0.1:9000/docs`
- Scenario: `http://127.0.0.1:9000/scenario`
- LaunchPilot OpenAPI: `http://127.0.0.1:8000/docs`

Mock 파일에는 실제 Client Secret이나 token을 넣지 않는다. `PLATFORM_MOCK_BASE_URL`은 token 유출을 막기 위해 localhost origin만 허용한다. 시나리오의 7월 17일 Meta 소재 피로 사건은 Retrieval Eval에도 재사용한다.

## Verification

| 범위 | 상태 |
| --- | --- |
| Google 로그인·YouTube OAuth/Analytics | 실제 계정 E2E 완료 |
| Google Ads·Meta Ads 정규화 | fixture 완료, 실제 광고 자산 검증 대기 |
| PostgreSQL 영속화·Structured Retrieval | 실제 dialect·권한 격리 검증 완료 |
| Elasticsearch BM25·원문 resolve | 실제 검색 검증 완료 |
| Chunker × Retriever Eval | tune 70/70, validation 12/12, holdout 1/1 완료 |
| LangGraph tool loop | LLM fixture 완료, 실모델 검증 대기 |

## Test

```bash
docker compose up -d postgres elasticsearch
.venv/bin/pytest
```

## Synthetic PostgreSQL marketing data

Retrieval experiments can use deterministic synthetic campaign data that is kept
separate from real platform ingestion by the `synthetic-marketing-v1` provenance
prefix and a dedicated synthetic user. The default seed creates 3 workspaces,
300 campaigns, and 90 daily observations per campaign.

```bash
launchpilot-seed-synthetic --dry-run
launchpilot-seed-synthetic --replace
```

If port 5432 is already occupied, start the project database on another port and
pass the matching URL to the seeder:

```bash
POSTGRES_PORT=55432 docker compose up -d postgres
launchpilot-seed-synthetic \
  --database-url postgresql://launchpilot:launchpilot-local@localhost:55432/launchpilot \
  --replace
```

Scale and repeatability are configurable:

```bash
launchpilot-seed-synthetic \
  --workspaces 5 \
  --campaigns-per-workspace 200 \
  --days 180 \
  --seed 20260813 \
  --replace
```

`--replace` deletes only workspaces owned by the dedicated synthetic user. It
does not delete real users, workspaces, campaigns, or platform observations.

## Evaluation

현재 정문은 tool별 Golden V1/V2가 아니라 task-centric `evals/datasets/`다. 동일한
Problem/Spec/World에서 시스템 조건만 바꾸고 paired multi-trial로 비교한다. 과거
retrieval matrix와 Golden V1/V2 명령은 재현용 archive이며 새 architecture release
decision의 입력으로 사용하지 않는다. dataset, Gemini judge, controlled runner의 현재
구조와 실행법은 [Eval README](evals/README.md)와 [Judge handoff](evals/JUDGE.md)에 있다.

테스트는 별도 `launchpilot_test` PostgreSQL DB를 사용한다.
