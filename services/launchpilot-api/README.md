# LaunchPilot API

Phase 1의 도메인 모델을 HTTP 경계로 검증하는 FastAPI 서비스다.

현재 제공하는 기능은 Campaign 생성, Campaign별 Conversation 생성, Observation 조회다. 에이전트 실행과 외부 플랫폼 인증·수집은 각각 Phase 3, Phase 1.5에서 연결한다.

## Run

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/uvicorn launchpilot.main:app --reload
```

OpenAPI UI: `http://127.0.0.1:8000/docs`

