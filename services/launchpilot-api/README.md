# LaunchPilot API

Phase 1의 도메인 모델을 HTTP 경계로 검증하는 FastAPI 서비스다.

현재 제공하는 기능은 Campaign 생성, Campaign별 Conversation 생성, Observation 조회와 YouTube 읽기 연결이다. 에이전트 실행은 Phase 4에서 연결한다.

## Run

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/uvicorn launchpilot.main:app --reload --env-file .env
```

OpenAPI UI: `http://127.0.0.1:8000/docs`

## Phase 2: local OAuth setup

Google Cloud Console에서 **YouTube Data API v3**와 **YouTube Analytics API**를 활성화하고, 로컬 Web OAuth redirect URI를 정확히 두 개 등록한다.

```text
http://127.0.0.1:8000/auth/google/callback
http://127.0.0.1:8000/connections/youtube/callback
```

발급받은 Client ID와 Client Secret은 Git에 올리지 않고 이 디렉터리의 `.env`에 저장한다. `.env.example`을 복사한 뒤 값을 채운다.

```dotenv
GOOGLE_OAUTH_CLIENT_ID="발급받은 Client ID"
GOOGLE_OAUTH_CLIENT_SECRET="발급받은 Client Secret"
```

나머지 두 비밀값은 서로 다르게 생성한다.

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

첫 번째 결과는 `APP_SESSION_SECRET`, 두 번째 결과는 `TOKEN_ENCRYPTION_KEY`에 넣는다.

배포 주소를 사용할 때는 두 callback의 앞부분을 실제 HTTPS 주소로 바꾸고 `COOKIE_SECURE=true`로 설정한다.

`GET /auth/google/login`은 앱 로그인만 수행한다. 로그인 후 `GET /connections/youtube/authorize`에서 별도로 YouTube 읽기 권한을 부여한다. OAuth 요청은 서명된 브라우저 쿠키와 PKCE로 보호한다. 액세스·리프레시 토큰은 응답에 노출하지 않으며, 로컬 SQLite 제어 저장소에 암호화해 보관하고 만료 전에 갱신한다.

`POST /campaigns/{campaign_id}/observations/youtube`가 실제 수집 진입점이다. 이는 추후 Agent가 사용자 의도와 권한을 확인한 다음 호출할 도구이며, 예약 수집은 하지 않는다.
