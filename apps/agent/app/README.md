# app — 에이전트 서비스 전체 지도

캠페인 분석 에이전트의 파이썬 코드. Java가 사용자 메시지를 보내면, 이 서비스가
LLM(Gemini)을 돌려 신호 분석 → 가설 → 실험 계획 → 승인을 진행하고, 결과를
실시간 블록으로 되돌려준다.

## 한 턴(turn)이 흐르는 길

```
Java
 │  POST /internal/agent/turns        (사용자 메시지 한 번)
 ▼
api/turns.py ── 접수(202) 후 백그라운드로 처리 시작
 │
 ▼
orchestrator.py ── 턴 1개 처리 진입점 (락 잡고 워크플로 실행)
 │
 ▼
orchestration/ ── 턴 처리 오케스트레이션
 │   1) 상태 불러오기   (runtime/)
 │   2) 의도 해석       (agents/ 인터프리터)
 │   3) 상태 확정       (runtime/transitions 리듀서)
 │   4) 라우팅 → 라운드 실행 (orchestration/phases/)
 │        └ LLM 일꾼 호출 (agents/) + 근거 조회 (tools/)
 │   5) 상태 저장       (runtime/ 저장소)
 │   6) 체크포인트       (runtime/episode)
 │
 ▼
화면 블록 생성 (runtime/blocks) ──▶ api/thread_stream.py (WebSocket) ──▶ Java
                                       (모든 단계가 흐르는 동안 tracing/ 으로 관측)
```

## 폴더 한눈에

| 폴더 | 한 줄 역할 | 비유 |
|---|---|---|
| [api/](api/) | Java와 주고받는 입구 (REST로 받고 WS로 흘려보냄) | 접수창구 |
| [orchestration/](orchestration/) | 한 턴을 어떤 순서로 처리할지 지휘 | 지휘자 |
| [orchestration/phases/](orchestration/phases/) | 한 단계(분석/가설/계획)를 실제로 실행 | 실무 라운드 |
| [agents/](agents/) | LLM(Gemini) 일꾼들 — 분석가/전략가/작성자 | 전문가 팀 |
| [runtime/](runtime/) | 대화 상태 + 저장소 + 과거 기록 | 기억 창고 |
| [tools/](tools/) | 근거 데이터 조회 (Elastic) | 자료 조사원 |
| [contracts/](contracts/) | 주고받는 데이터의 모양(스키마) 정의 | 표준 양식 |
| [tracing/](tracing/) | 무슨 일이 있었는지 추적 기록(관측) | CCTV |
| [eval/](eval/) | 결과 품질 측정 (LLM 심사) | 품질검사 |

## 루트 파일

| 파일 | 한 줄 역할 |
|---|---|
| [main.py](main.py) | FastAPI 앱 구동 + 로깅 설정 |
| [orchestrator.py](orchestrator.py) | 턴 1개 처리 진입점 (얇은 껍데기) |
| [config.py](config.py) | 환경설정 (Gemini/Elastic/Redis 키 등) |
| [ids.py](ids.py) | id/시간 생성 헬퍼 |
| [observability.py](observability.py) | 추적(Phoenix) 켜기 |
| [GLOSSARY.md](GLOSSARY.md) | 코드 단어 → 일상어 사전 (읽다 막히면 여기) |

> 처음 읽는다면: 이 표 → [orchestration/README.md](orchestration/README.md) 순서를 권한다.
