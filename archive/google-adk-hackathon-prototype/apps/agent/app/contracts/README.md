# contracts — 주고받는 데이터의 모양

Java·프런트와 주고받는 모든 데이터의 표준 양식(스키마)을 한곳에 모은 곳.
여기 정의가 "약속한 모양"이고, 어긋나면 거절한다.

## 무엇을 정의하나

```
도메인 객체 : Signal(신호) / Hypothesis(가설) / ExperimentPlan(실험계획) ...
일꾼 출력  : SignalDraftOutput / HypothesisDraftOutput / ...  (LLM이 돌려줄 모양)
API 입출력 : InternalAgentTurn(들어오는 턴) / 스트림 메시지 / 에러 봉투
검증 결과  : ValidationReport / ValidationIssue
```

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [schemas.py](schemas.py) | 모든 계약 모델(pydantic). 실제 원본은 저장소 루트 `contracts/` JSON |

## 핵심 원칙

- **단일 진실.** 이 모델이 모양의 기준. 일꾼 결과도 이 모델로 재검증한다.
- **엄격.** 대부분 `extra="forbid"` — 약속에 없는 필드는 거절(오타·헛것 차단).
