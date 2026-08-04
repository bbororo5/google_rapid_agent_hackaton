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
