# LaunchPilot API

Phase 1의 도메인 모델을 HTTP 경계로 검증하는 FastAPI 서비스다.

현재 제공하는 기능은 Campaign 생성, Campaign별 Conversation 생성, Observation 조회와 YouTube 읽기 연결이다. 에이전트 실행은 Phase 3에서 연결한다.

## Run

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/uvicorn launchpilot.main:app --reload
```

OpenAPI UI: `http://127.0.0.1:8000/docs`

## Phase 1.5: local OAuth setup

Google Cloud Console에서 **YouTube Data API v3**와 **YouTube Analytics API**를 활성화하고 Web OAuth redirect URI를 아래와 같이 등록한다.

```bash
export GOOGLE_OAUTH_CLIENT_ID="..."
export GOOGLE_OAUTH_CLIENT_SECRET="..."
export TOKEN_ENCRYPTION_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export PUBLIC_BASE_URL="http://127.0.0.1:8000"
```

`GET /auth/google/login`은 앱 로그인만 수행한다. 로그인 후 `GET /connections/youtube/authorize`에서 별도로 YouTube 읽기 권한을 부여한다. 액세스·리프레시 토큰은 응답에 노출하지 않으며, 로컬 SQLite 제어 저장소에 암호화해 보관한다.

`POST /campaigns/{campaign_id}/observations/youtube`가 실제 수집 진입점이다. 이는 추후 Agent가 사용자 의도와 권한을 확인한 다음 호출할 도구이며, 예약 수집은 하지 않는다.
