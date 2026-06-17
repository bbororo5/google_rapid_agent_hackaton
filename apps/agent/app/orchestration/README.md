# orchestration — 한 턴을 지휘하는 곳

사용자 메시지 한 번(turn)을 받아 "해석 → 판정 → 실행 → 저장" 순서로 처리한다.
세부 일은 다른 폴더(agents/runtime/phases)에 맡기고, 여기는 **순서만** 지휘한다.

## 처리 순서 (workflow.py 가 줄거리)

```
TurnWorkflow.run(record, content)
 │
 ├─ 1. loader      상태/스코프/기억 불러오기        (context.py)
 ├─ 2. interpreter 자유 문장 → "무슨 뜻"으로 해석   (interpreter.py → agents/)
 │        └ reducer 가 그 해석을 실제 상태로 확정    (runtime/transitions.py)
 ├─ 3. router      판정에 따라 처리기로 보냄          (router.py)
 │        └ 라운드 실행                              (phases/)
 ├─ 4. committer   바뀐 상태를 저장소에 기록          (committer.py)
 └─ 5. checkpointer 되돌리기용 스냅샷 남김            (checkpoint.py)
```

전 과정의 화면 출력은 emitter.py 한곳을 통해 나간다.

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [workflow.py](workflow.py) | 전체 줄거리 (위 5단계를 순서대로 호출) — **여기부터 읽기** |
| [context.py](context.py) | 1단계: 상태·캠페인·최근 대화 불러오기 + LLM에 줄 컨텍스트 조립 |
| [interpreter.py](interpreter.py) | 2단계: 사용자 문장을 의도(변경안)로 해석하고 리듀서로 확정 |
| [router.py](router.py) | 3단계: 처리 방식(직접답변/라운드실행/되묻기/위임)별로 분기 |
| [phases/](phases/) | 라운드 실행기 모음 (분석/가설/계획). 별도 README 있음 |
| [committer.py](committer.py) | 4단계: 바뀐 상태를 저장소+캐시에 기록 (충돌 시 안내) |
| [checkpoint.py](checkpoint.py) | 5단계: 이번 라운드를 에피소드로 남겨 되돌리기 지점 생성 |
| [emitter.py](emitter.py) | 화면 블록(진행상황/텍스트/에러)을 내보내는 단일 창구 |
| [models.py](models.py) | 이 폴더가 공유하는 객체 (TurnContext/TurnDecision/TurnOutcome) |

## 핵심 원칙

- **LLM은 제안, 코드가 확정.** 인터프리터(LLM)는 "이렇게 하자"를 제안만 하고,
  실제 상태 변경은 리듀서(runtime/transitions.py)라는 코드가 판정한다.
- **지휘와 실무 분리.** 이 폴더는 순서만. 실제 LLM 호출/저장은 agents/·runtime/.
