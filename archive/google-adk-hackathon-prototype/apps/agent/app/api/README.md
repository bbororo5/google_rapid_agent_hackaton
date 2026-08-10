# api — Java와 주고받는 입구

받는 곳과 보내는 곳이 나뉘어 있다.

```
Java ──POST /internal/agent/turns──▶ turns.py      (메시지 받기, 202 즉시 응답)
Java ◀──WS /threads/{id}/stream───── thread_stream.py (결과 블록 흘려보내기)
```

받기는 REST(한 번씩), 보내기는 WebSocket(계속 스트리밍)으로 분리돼 있다.
turns.py는 메시지를 접수만 하고 실제 처리는 백그라운드로 넘긴다 — 처리 결과는
thread_stream.py 소켓으로 흘러나온다.

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [turns.py](turns.py) | 사용자 메시지 접수 (REST). 검증 후 백그라운드 처리 시작 |
| [thread_stream.py](thread_stream.py) | 화면 블록 스트림 (WebSocket). 접속 시 과거분 재생 후 실시간 전송 |
