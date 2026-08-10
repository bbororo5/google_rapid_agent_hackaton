# LaunchPilot API

여러 광고 플랫폼의 Campaign 성과를 하나의 불변 Observation으로 수집하는 FastAPI 서비스다. 현재 Agent 실행은 포함하지 않으며 Phase 5에서 LangGraph로 연결한다.

## Run

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
.venv/bin/uvicorn launchpilot.main:app --reload --env-file .env
```

OpenAPI UI: `http://127.0.0.1:8000/docs`

## Secret generation

다음 두 값을 별도로 생성해 `.env`에 넣는다.

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

- 첫 번째 값: `APP_SESSION_SECRET`
- 두 번째 값: `TOKEN_ENCRYPTION_KEY`
- Google/Meta가 발급한 Secret과 재사용하지 않는다.
- `.env`는 Git에 커밋하지 않는다.

## OAuth callbacks

Google Cloud Console에 다음 callback을 등록한다.

```text
http://127.0.0.1:8000/auth/google/callback
http://127.0.0.1:8000/connections/youtube/callback
http://127.0.0.1:8000/connections/google-ads/callback
```

Meta for Developers 앱에는 다음 callback을 등록한다.

```text
http://127.0.0.1:8000/connections/meta-ads/callback
```

HTTPS 배포 환경에서는 앞부분을 실제 도메인으로 바꾸고 `COOKIE_SECURE=true`로 설정한다.

## Required platform setup

### YouTube

- YouTube Data API v3 활성화
- YouTube Analytics API 활성화
- OAuth test user 등록

### Google Ads

- Google Ads API 활성화
- Google Ads Manager Account의 API Center에서 Developer Token 발급
- OAuth scope: `https://www.googleapis.com/auth/adwords`

### Meta Ads

- Meta 앱 생성
- Marketing API 사용 설정
- 최소 읽기 권한: `ads_read`
- 개발 모드에서는 앱 역할과 테스트 가능한 광고 자산을 연결

## User flow

```text
GET /auth/google/login
→ LaunchPilot 로그인

GET /connections/{provider}/authorize
→ 플랫폼 읽기 권한 승인

GET /connections/{connection_id}/accounts
→ 접근 가능한 광고 계정 선택

GET /connections/{connection_id}/campaigns?account_ref=...
→ 외부 광고 Campaign 선택

POST /campaigns/{campaign_id}/bindings
→ LaunchPilot Campaign에 외부 Campaign 연결

POST /campaigns/{campaign_id}/observations/ads
→ 연결된 광고 플랫폼을 함께 수집
```

한 플랫폼만 실패하면 성공한 Slice를 `PARTIAL` Observation으로 보존한다. 모든 플랫폼이 실패하면 빈 Observation을 만들지 않는다. 예약 수집은 하지 않으며 사용자의 분석 요청 시점에만 실행한다.

Campaign, Conversation, CampaignObservation은 SQLite에 영속화한다. Observation은 PlatformSlice와 MetricObservation으로 정규화해 저장하므로 서버 재시작 후에도 조회할 수 있고 다음 Retrieval 단계에서 구조화 검색의 기준 데이터가 된다.

## Local platform mock

실제 광고 계정이나 캠페인이 없어도 전체 수집 흐름을 반복 검증할 수 있는 별도 FastAPI 서버를 제공한다. mock은 `LunchPilot 여름 신규고객 캠페인` 하나를 다음처럼 일관되게 표현한다.

- Google Ads: 검색·영상 광고의 계정, Campaign, 구매 성과
- Meta Ads: Reels·Feed 광고의 계정, Campaign, 구매 성과
- YouTube: 같은 기간 캠페인을 지원한 소유 채널 콘텐츠 성과

YouTube Analytics에는 광고 Campaign 개념이 없으므로 억지로 광고 데이터로 취급하지 않는다. YouTube 광고 성과는 Google Ads에 속하고, YouTube 채널 지표는 같은 비즈니스 Campaign의 콘텐츠 문맥으로 수집한다.

첫 번째 터미널에서 mock 서버를 실행한다.

```bash
.venv/bin/uvicorn launchpilot.mock_platforms.main:app --port 9000
```

실제 플랫폼 자격증명이 든 `.env`를 재사용하지 말고 mock 전용 파일을 만든다.

```bash
cp .env.mock.example .env.mock
```

이 모드에서는 Google 로그인과 YouTube·Google Ads·Meta Ads 권한 승인이 mock OAuth로 즉시 돌아온다. Google·Meta Client ID, Client Secret, Developer Token은 필요하지 않으며 실제 값을 mock 파일에 넣어서는 안 된다.

실제 토큰이 임의 서버로 전달되는 설정 사고를 막기 위해 `PLATFORM_MOCK_BASE_URL`은 localhost origin만 허용한다.

두 번째 터미널에서 API를 실행한다.

```bash
.venv/bin/uvicorn launchpilot.main:app --reload --env-file .env.mock
```

- mock OpenAPI: `http://127.0.0.1:9000/docs`
- 캠페인 시나리오: `http://127.0.0.1:9000/scenario`
- LaunchPilot OpenAPI: `http://127.0.0.1:8000/docs`

시나리오에는 7월 17일부터 Meta 소재 피로로 CTR과 구매율이 하락하는 사건을 포함했다. 따라서 API 연결 성공뿐 아니라 이후 Retrieval과 Eval에서 기간 비교·이상 징후 설명을 검증하는 기준 데이터로 재사용할 수 있다.

## Verification status

| 범위 | 검증 상태 |
| --- | --- |
| Google 로그인·HMAC 세션·Workspace | 실제 계정 E2E 완료 |
| YouTube OAuth·토큰 암호화·갱신 | 실제 계정 E2E 완료 |
| YouTube 채널·Analytics 수집 | 실제 API E2E 완료 |
| Google Ads 정규화 | MockTransport fixture 완료, Developer Token 연결 대기 |
| Meta Ads 정규화 | MockTransport fixture 완료, Meta 앱 연결 대기 |
| 멀티플랫폼 partial failure | application service fixture 완료 |
| Campaign·Conversation·Observation 영속화 | repository 재생성·서버 재시작 검증 완료 |
