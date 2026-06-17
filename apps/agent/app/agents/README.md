# agents — LLM(Gemini) 일꾼 팀

실제 Gemini를 호출하는 곳. 각 일꾼은 한 가지 역할만 하고, 결과를 정해진
모양(스키마)으로 돌려준다. 오케스트레이션은 [workers.py](workers.py) 한 창구만 본다.

## 일꾼 명단

```
인터프리터 (interpreter) ── 사용자 문장 → 의도(변경안)
분석가     (analyst)     ── 지표 → 신호        + 근거조회 도구 사용
전략가     (strategist)  ── 신호 → 가설        + 팀노트 도구 사용
작성자     (writer)      ── 가설 → 실험계획
챗        (chat)        ── 자유 대화 답변
```

## 호출 경로

```
phases/ (라운드)
   │  workers.run_analyst / run_strategist / run_writer ...   ← 유일한 입구
   ▼
workers.py  ── 프롬프트 조립 + 결과를 계약 모델로 재검증
   │
   ▼
adk_agents.py ── 실제 ADK/Gemini 실행 (타임아웃·세션 처리)
   │
   ▼
Gemini  (+ 도구 호출 시 tools/ 의 근거 조회)
```

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [workers.py](workers.py) | 일꾼 호출 창구 — 프롬프트 만들고 결과를 계약 모델로 검증 |
| [adk_agents.py](adk_agents.py) | 실제 ADK/Gemini 에이전트 구성 + 실행(타임아웃 포함) |
| [instructions.py](instructions.py) | 각 일꾼의 시스템 지침(역할 규칙) 텍스트 |
| [output_schemas.py](output_schemas.py) | 일꾼이 돌려줄 결과의 모양(구조화 출력 스키마) |
| [formatter.py](formatter.py) | 세 결과(신호/가설/계획)를 최종 payload로 조립 (LLM 아님) |
| [reviewer.py](reviewer.py) | 계획 승인 가드레일 — 기계적 검사. LLM이 못 뒤집음 |
| [reflection.py](reflection.py) | 과거 실패 패턴을 Phoenix에서 읽어 참고용으로 요약(권고만) |

## 핵심 원칙

- **검증은 코드.** reviewer/formatter는 LLM이 아니라 결정적 코드다. LLM 결과의
  모양·정합성은 코드가 최종 판정한다.
- **창구 단일화.** phases는 workers만 안다. ADK/Gemini 세부는 adk_agents에 숨김.
