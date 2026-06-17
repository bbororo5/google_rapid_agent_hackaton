# tools — 근거 데이터 조회원

LLM 일꾼이 "이 지표가 실제로 얼마나 올랐나?"를 물을 때, 진짜 데이터(Elastic)에서
근거를 가져오는 도구들. 근거는 절대 지어내지 않는다 — 없으면 보이는 에러로.

## 조회 경로 (2단 폴백)

```
agents/ 일꾼이 도구 호출
   │
   ▼
evidence.py  ── 도메인 안전 도구 4종 (정규화된 근거 dict 반환)
   │   1순위
   ├─▶ mcp_client.py + mcp_bridge.py  (Elastic MCP 서버, ES|QL)
   │   실패 시 2순위
   └─▶ es_client.py                    (Elastic 직접 조회, httpx)
```

LLM은 원시 쿼리(ES|QL)나 전송 계층을 절대 보지 않는다 — 정규화된 근거만 받는다.

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [evidence.py](evidence.py) | 일꾼이 부르는 근거 도구 4종 (지표 기준선/콘텐츠/팀노트/브리프) |
| [mcp_client.py](mcp_client.py) | Elastic MCP 서버에 고정 ES|QL로 질의 (1순위 경로) |
| [mcp_bridge.py](mcp_bridge.py) | 동기 도구 ↔ 비동기 MCP 서버 연결 (서버 1개 재사용) |
| [es_client.py](es_client.py) | Elastic 직접 조회 (MCP 실패 시 2순위 경로) |

## 핵심 원칙

- **근거는 사실만.** 로컬에서 지어내지 않는다. 설정 없으면 명시적 에러.
- **쿼리는 코드가 작성.** ES|QL은 wrapper가 고정 작성, LLM이 쓰지 않는다.
