# LLM 지연 PoC 계획 (이슈 #13)

- **상태(Status):** 제안됨 (PoC 범위)
- **날짜(Date):** 2026년 6월 29일
- **범위(Scope):** 분석 단계가 느린 문제. Python Agent Core의 한 턴(analyst -> strategist -> writer -> reviewer) 중 analyst 구간
- **추적(Tracking):** GitHub 이슈 #13 "LLM Latency PoC"
- **관련 문서:** [orchestrator-latency-before-refactor.md](orchestrator-latency-before-refactor.md), [observability-telemetry-plan.md](observability-telemetry-plan.md), [adr/07-unified-observability.md](adr/07-unified-observability.md)

## 0. 용어 한 줄 정리

본문에 들어가기 전에 자주 나오는 말부터 풀어둔다.

- **턴(turn):** 사용자가 메시지 하나 보내고 답을 받기까지의 한 사이클.
- **analyst / strategist / writer / reviewer:** 한 턴 안에서 차례로 일하는 4명의 일꾼(worker). analyst는 데이터에서 신호를 찾고, strategist는 가설을 세우고, writer는 결과를 글로 쓰고, reviewer는 마지막에 규칙대로 검사한다.
- **ADK:** 구글의 에이전트 프레임워크. 모델이 "도구를 쓸지, 답을 낼지"를 스스로 정하며 여러 번 왔다 갔다 할 수 있다.
- **function call(함수 호출 / 도구 호출):** 모델이 "이 데이터 좀 가져와" 하고 도구를 부르는 행위. 한 번 부를 때마다 외부에 다녀오는 왕복 비용이 든다.
- **self-correction 루프:** 모델이 한 번에 끝내지 못하고 "찾아보고 -> 보고 -> 다시 찾아보고"를 반복하는 것. 횟수가 많을수록 느려진다.
- **telemetry / span / trace:** 시스템이 "언제 무엇을 얼마나 했는지" 남기는 계측 기록. span은 한 작업 구간, trace는 그 구간들을 한 턴으로 엮은 것.
- **TTFT(time to first token):** 모델이 첫 글자를 내뱉기까지 걸리는 시간.

## 1. 한 줄 문제와 이 문서의 목적

데이터 분석 단계가 너무 느리다. 한 턴에서 analyst가 혼자 약 50초를 먹는다.
사용자는 그동안 빈 화면을 보며 기다린다.

이슈 #13은 그 원인을 "모델이 확률적 출력을 결정적 결과로 바꾸려고 반복 루프를 도는
탓"이라 추정하고 세 단계 해법을 제시한다. 다만 이 가설은 일반론이라, 우리 시스템에
그대로 맞는지 먼저 확인해야 한다.

그래서 이 PoC의 원칙은 **"고치기 전에 먼저 측정한다"** 이다. 추측으로 코드를 바꾸지
않는다. 무엇을 측정하고, 어디까지 손대고, 각 단계가 끝나면 그림이 어떻게
바뀌는지를 이 문서에서 정의한다. 실제 계측 코드와 프로파일러는 4절 관측 단계를 마친 뒤 이 브랜치에
올라온다.

## 2. 어디까지 할지 (범위)

이번 PR에서 하는 것:

- **Stage 0 (검증):** 이미 깔린 측정 도구(PR #10-#12)로 한 턴을 들여다보고, 이슈 #13의
  가설이 우리한테 진짜 맞는지 판정한다.
- **Stage 1 (정량화):** "이 턴이 모델을 몇 번 불렀고, 도구를 몇 번 왕복했고, 어디서
  몇 초 썼는지"를 누구나 조회할 수 있는 숫자로 남긴다.
- **Stage 2 (경량화):** 모델이 데이터를 여러 번 뒤져 찾던 일을, 미리 계산해 요약으로
  건네주는 방식으로 바꿔 왕복 횟수를 줄인다.

이번 PR에서 안 하는 것:

- **Stage 3 (작은 모델 도입):** 코드 생성용으로 더 작은/특화 모델을 쓰는 실험. 후속 이슈로
  미룬다. (먼저 측정과 경량화로 얼마나 빨라지는지 본 뒤 판단하는 게 순서다.)

## 3. 이슈 #13의 가설을 우리 현실로 번역

이슈 #13은 "프롬프트에 raw CSV를 통째로 넣고 -> 모델이 Python 코드를 만들고 ->
실행하고 -> 에러 나면 고치는" 흐름을 전제로 쓰였다. 그런데 LaunchPilot은 그렇게
동작하지 않는다. 그래서 가설을 검증하려면 먼저 우리 구조로 옮겨 적어야 한다.

| 이슈 #13 주장 | LaunchPilot의 실제 모습 | 우리한테 맞나? |
| --- | --- | --- |
| 순차적인 생성-실행-수정 루프가 지연을 지배한다 | analyst는 한 번 일하는 동안 도구를 **6번** 부르는 ADK 루프다(약 52.8초). 게다가 analyst -> strategist -> writer가 한 줄로 줄 서서 차례로 실행된다. [orchestrator-latency-before-refactor.md](orchestrator-latency-before-refactor.md) 5.5-5.6절. | 맞다. 단, "코드를 고치는" 루프가 아니라 "도구를 반복 호출하는" 루프 형태로. |
| raw CSV 주입이 입력 토큰과 첫 응답 시간(TTFT)을 늘린다 | 우리는 CSV를 프롬프트에 넣지 않는다. CSV는 Java가 받아 Elastic에 저장하고, analyst는 도구로 필요한 근거만 꺼내 쓴다(`apps/agent/app/agents/workers.py`, `apps/agent/app/tools/evidence.py`). | 절반만. raw CSV 문제는 없지만, "필요한 걸 도구로 여러 번 찾는다"는 점은 같다. 그래서 경량화의 대응책은 "미리 계산한 요약을 건네기"가 된다. |
| 확률적 모델에 결정적 코드를 강제하는 게 본래 비효율이다 | analyst 하나가 탐색가 + 도구 호출자 + 데이터 분석가 + 근거 선별자 + JSON 생성기를 한 호출에 다 겸한다(latency 문서 6절). | 맞다. latency 문서의 결론(9절: 후보는 Python이 미리 계산하고, 모델은 그 후보를 해석만 하라)과 정확히 같은 진단이다. |

**Stage 0에서 확인할 한 문장:** 진짜 비용은 "CSV 토큰 양"이 아니라 "analyst가 근거를
여러 번 찾아다니는 루프 + 단계들이 한 줄로 줄 서서 기다리는 직렬 구조"다.

## 4. Stage 0 - 이미 있는 측정값으로 먼저 검증

목표: 코드를 건드리기 전에 병목을 눈으로 확인한다. PR #10-#12에서 Java와 Python을
하나의 턴으로 엮어 보는 측정 baseline(로그/지표/추적/품질평가 4축)을 이미 깔아 뒀다.
같은 턴은 공통 ID(`trace_id`, `thread_id`, `request_id`, `workspace_id`,
`campaign_id`)로 연결된다.

대표 턴 하나를 골라 다음을 확인한다:

- [ ] 한 턴 전체 시간을 Java / Python / Elastic / 모델-도구 구간으로 쪼개 본다.
- [ ] 일꾼별 소요 시간(`worker <kind>: gemini call done in <n>ms`,
  `apps/agent/app/agents/adk_agents.py:167`).
- [ ] 그 턴에서 analyst가 도구를 몇 번 불렀는지(지금은 ADK 경고 로그로만 슬쩍 보이고,
  깔끔한 숫자로는 안 남는다).
- [ ] 근거 조회 도구를 몇 번 썼고 각각 몇 초였는지(`apps/agent/app/telemetry/service.py:50`).
- [ ] 정해 둔 예산 대비 실제 모델 호출 횟수(`goal.budgets.max_llm_calls`,
  `apps/agent/app/telemetry/service.py:99`).

**끝나면 달라지는 것:** "왜 느린지 모르겠다"가 사라진다. 3절 가설을 받아들일지 버릴지를
근거(추적/로그)와 함께 한 문단으로 결론 낸다. 이게 있어야 Stage 1, 2가 추측이 아니라
데이터 위에서 움직인다.

## 5. Stage 1 - 루프 횟수를 숫자로 남기기 (정량화)

**지금 문제:** analyst가 도구를 몇 번 도는지는 ADK가 흘리는 경고 로그로만 보인다.
"이번 턴은 몇 왕복 했나?"를 조회하거나 턴마다 추세로 비교할 방법이 없다. 느린 걸
느낌으로만 안다는 뜻이다.

**할 일:**

1. 일꾼 실행 루프(`apps/agent/app/agents/adk_agents.py`의 `run_structured` /
   `run_text`)에서 한 호출당 이벤트를 센다: 도구 호출 몇 번, 중간 모델 응답 몇 번,
   최종 응답. 지금 코드 `_collect()`는 마지막 응답만 챙기고 중간 것들은 버린다.
2. 그 숫자를 기존 telemetry 통로(`apps/agent/app/telemetry/service.py`)로 흘려보내,
   각 일꾼 기록에 다음을 붙인다: `agent.worker.llm_round_count`(모델 왕복 수),
   `agent.worker.function_call_count`(도구 호출 수), `agent.worker.elapsed_ms`(걸린 시간).
3. 턴 단위로 합산한다: 총 모델 호출 수, 총 도구 왕복 수, 단계별 시간 분해를
   `record_turn_outcome`에 기록.

**끝나면 달라지는 것:** 아무 턴이나 골라 "이 턴은 모델 N번, 도구 M번, analyst에서 몇 초"를
로그 뒤지지 않고 대시보드에서 바로 읽는다. Stage 2를 적용한 뒤 "정말 줄었나?"를 같은
숫자로 전후 비교한다. Stage 1은 곧 Stage 2의 성적표를 만드는 작업이다.

## 6. Stage 2 - analyst가 덜 헤매게 만들기 (경량화)

이슈가 말한 "데이터 프로파일링 + 컨텍스트 경량화"를 우리 구조(Elastic 근거 기반)에 맞춘
것이고, latency 문서 9절(4-5항)의 결론과 같은 방향이다.

**지금 문제:** analyst가 "어떤 지표가 중요하지? 어떤 채널이 잘 나갔지?"를 알아내려고
`query_metric_baseline`, `search_content_posts` 같은 도구를 여러 번 부른다. 매 호출이 외부
왕복이라, 6번이면 6번의 왕복 비용이 그대로 쌓인다.

**할 일:**

1. 그 탐색을 모델 대신 Python이 한 번에 한다. Elastic에서 캠페인의 지표/채널 윤곽을
   결정적으로 미리 계산한다(엑셀로 치면 `content_posts`에 대한 요약 통계 `df.info()` /
   `df.describe()`에 해당).
2. 그 짧은 요약을 "후보"로 analyst 프롬프트에 넣어 준다.
3. analyst(Flash)는 이제 처음부터 뒤지지 않고, 건네받은 후보를 해석/선택해 결과 스키마만
   만든다. 목표는 모델 왕복을 6번에서 1-2번으로 줄이는 것이다.

**끝나면 달라지는 것:** analyst의 도구 호출 수와 소요 시간이 Stage 0 baseline 대비 눈에
띄게 준다. 사용자 입장에선 분석 대기 시간이 짧아진다. 단, 빨라지자고 답 품질을 깎으면
안 되므로, reviewer/품질평가(4번째 축) 점수가 전후로 떨어지지 않는지 함께 확인한다.

## 7. 리스크와 주의

- Stage 2는 analyst가 근거를 모으는 경로를 바꾼다. 속도를 얻겠다고 답의 **근거(grounding)**
  품질을 잃으면 안 된다. 전후 품질을 반드시 비교한다.
- Stage 1 계측은 tracing이 꺼져 있어도 시스템을 깨지 않고 조용히 넘어가야 한다(기존
  telemetry 레이어 규칙과 동일).
- 모든 측정은 공통 ID를 재사용해 Java, Python, Elastic 시간이 같은 턴 위에서 줄 맞게 한다.

## 8. 완료 정의 (이번 PR)

- [ ] Stage 0 결론을 증거와 함께 기록(가설 수락 또는 기각).
- [ ] Stage 1 계측 머지, 턴마다 숫자가 보임.
- [ ] Stage 2 경량화 머지, 전후 속도/품질 비교표 첨부.
- [ ] Stage 3는 후속 이슈로 명시적으로 넘김.
