# LLM 지연 PoC 계획 (이슈 #13)

- **상태(Status):** 제안됨 (PoC 범위)
- **날짜(Date):** 2026년 6월 29일
- **범위(Scope):** Python Agent Core 턴 경로(analyst -> strategist -> writer -> reviewer)에서의 analyst 지연
- **추적(Tracking):** GitHub 이슈 #13 "LLM Latency PoC"
- **관련 문서:** [orchestrator-latency-before-refactor.md](orchestrator-latency-before-refactor.md), [observability-telemetry-plan.md](observability-telemetry-plan.md), [adr/07-unified-observability.md](adr/07-unified-observability.md)

## 1. 이 문서가 존재하는 이유

이슈 #13은 Analytics agent의 43초 초과 지연이 확률적 LLM 출력을 결정적 결과로
바꾸는 과정의 반복적 self-correction 루프에서 온다고 가정하고, 세 단계의 해결책을
제시한다. 수정 코드를 작성하기 전에, 이 PoC는 먼저 이슈의 일반적 가설이 LaunchPilot에서
실제로 관측되는 현상과 일치하는지 확인하고, 적용 가능한 단계만 골라 깊게 구현한다.

이 문서는 그 작업과 경계를 정의한다. 구현 자체는 아직 포함하지 않는다. 계측 코드와
프로파일러는 4절의 관측 단계 이후 이 브랜치에 올라온다.

## 2. 범위

이번 PR 포함 범위:

- Stage 0 (검증): PR #10-#12에서 구축한 기존 telemetry를 관측하고, 이슈 #13의
  가설이 우리 아키텍처에 성립하는지 판단한다.
- Stage 1 (정량화): self-correction 루프, LLM 호출 수, 턴당 타이밍을 일급(first-class)
  telemetry로 만들어 질의 가능하게 한다.
- Stage 2 (경량화): 후보를 결정적으로 선계산하고, 모델이 모든 것을 tool call로
  발견하게 두는 대신 메타데이터 요약을 주입해 analyst의 턴당 LLM/tool round 수를 줄인다.

이번 PR 제외 범위:

- Stage 3 (코드 생성용 소형/태스크 특화 모델). 후속 작업으로 연기.

## 3. 가설 매핑: 이슈 #13 vs LaunchPilot 현실

이슈 #13은 "프롬프트에 raw CSV 주입 -> Python 생성 -> 실행 -> 에러 시 수정" 패턴을
전제로 작성됐다. LaunchPilot은 그렇게 동작하지 않으므로, 가설을 검증하기 전에 먼저
우리 구조로 번역해야 한다.

| 이슈 #13 주장 | LaunchPilot 현실 | 적용 여부 |
| --- | --- | --- |
| 순차적 generate-execute-fix 루프가 지연을 지배 | analyst는 한 worker 호출에서 **function call 6개**를 방출한 ADK agent 루프(약 52.8초)이며, 오케스트레이터는 analyst -> strategist -> writer를 직렬 실행. [orchestrator-latency-before-refactor.md](orchestrator-latency-before-refactor.md) 5.5-5.6절 참조. | 예. 단 code-fix 루프가 아니라 tool/model-round 루프로서. |
| raw CSV 주입이 입력 토큰과 TTFT를 부풀림 | CSV는 Java가 파싱해 Elastic에 적재. analyst 프롬프트는 CSV 행이 아니라 사용자 요청과 날짜 범위를 담음(`apps/agent/app/agents/workers.py`). evidence는 Elastic tool로 조회(`apps/agent/app/tools/evidence.py`). | 부분적. raw CSV 프롬프트는 없으나, analyst가 여전히 반복 tool call로 evidence를 발견함. 경량화의 대응물은 선계산된 후보 요약. |
| 확률적 모델에 결정적 코드를 강제하는 것 자체가 비효율 | analyst가 한 호출 안에서 explorer + tool caller + 데이터 분석가 + evidence 선택자 + 구조화 JSON 생성기로 동시에 쓰임(latency 문서 6절). | 예. latency 문서의 리팩터 함의(9절: metric/channel 후보를 결정적으로 계산하고, Flash로 선계산 후보를 해석)와 일치. |

Stage 0에서 검증할 결론: 실제 비용은 raw-CSV 토큰 양이 아니라, analyst의 다중 round
evidence 발견 루프 + phase 직렬 실행이다.

## 4. Stage 0 - 기존 telemetry 대조 검증

목표: 코드를 바꾸기 전에 병목을 확인한다. PR #10-#12는 Java와 Python을 가로질러
공유 상관 필드(`trace_id`, `thread_id`, `request_id`, `workspace_id`, `campaign_id`)로
연결된 4축 관찰성 baseline(logs, metrics, traces, evals)을 구축했다.

대표 E2E 턴 1건에 대한 관측 체크리스트:

- [ ] End-to-end 턴 지연을 Java / Python / Elastic / LLM-tool로 분해.
- [ ] worker별 지연(`worker <kind>: gemini call done in <n>ms`,
  `apps/agent/app/agents/adk_agents.py:167`).
- [ ] 해당 턴의 analyst function-call 수(현재는 구조화 telemetry가 아니라
  ADK "non-text parts" 경고로만 보임).
- [ ] evidence tool 호출 횟수와 각각의 지연(retriever span,
  `apps/agent/app/telemetry/service.py:50`).
- [ ] goal 예산 대비 실제 LLM 호출 수(`goal.budgets.max_llm_calls`,
  `apps/agent/app/telemetry/service.py:99`).

종료 기준: 3절의 매핑된 가설을 수락 또는 기각하는 한 문단 결론과, 그 근거가 되는
trace/log 증거 첨부.

## 5. Stage 1 - self-correction 루프 정량화

문제: 오늘날 analyst의 루프 크기는 비구조화 ADK 경고로만 관측된다. "이 턴이 몇 번의
model/tool round를 거쳤는가"를 질의하거나 턴 간 추세로 볼 수 없다.

계획:

1. worker 실행 루프(`apps/agent/app/agents/adk_agents.py`의 `run_structured` /
   `run_text`)에서 호출당 ADK 이벤트를 카운트: function-call 이벤트(tool round),
   중간 model 응답, 최종 응답. 현재 `_collect()`는 `is_final_response()`만 보관하고
   나머지는 버린다.
2. 기존 telemetry facade(`apps/agent/app/telemetry/service.py`)로 카운트를 방출해,
   각 worker span이 다음을 담게 한다: `agent.worker.llm_round_count`,
   `agent.worker.function_call_count`, `agent.worker.elapsed_ms`.
3. 턴 span으로 집계: 총 LLM 호출 수, 총 tool round 수, phase별 타이밍 분해를
   `record_turn_outcome`에 기록.

성공 지표: 임의의 턴에 대해 루프 수, LLM 호출 수, phase별 타이밍 분해를 경고 grep
없이 telemetry에서 바로 읽을 수 있다.

## 6. Stage 2 - analyst 컨텍스트 경량화

이슈의 "데이터 프로파일링과 컨텍스트 경량화" 단계를 Elastic-evidence 아키텍처에 맞게
적용한 것이며, latency 문서의 리팩터 함의(9절 4-5항)와 일치한다.

계획:

1. analyst가 여러 번의 `query_metric_baseline` / `search_content_posts` tool call로
   발견하게 두는 대신, Python에서 캠페인의 metric/channel 프로파일을 Elastic으로부터
   결정적으로 선계산한다(`content_posts`에 대한 `df.info()` / `df.describe()` 대응물).
2. 그 압축된 프로파일 요약을 선계산 후보로서 analyst 프롬프트에 주입한다.
3. analyst(Flash)는 선계산 후보로부터 해석/선택해 구조화 signal schema를 생성하는 데만
   쓰고, model round를 6회가 아니라 1-2회로 목표한다.

성공 지표: Stage 0 baseline 대비 analyst function-call 수와 analyst 지연이 유의미하게
감소하되, reviewer/eval 품질(4번째 관찰성 축)에 회귀가 없어야 한다.

## 7. 리스크와 주의

- Stage 2는 analyst의 evidence 경로를 바꾼다. 지연 이득이 grounding 품질을 희생하지
  않도록 reviewer/eval 품질을 전후 비교해야 한다.
- Stage 1은 tracing 비활성 시에도 no-op으로 안전해야 하며, 기존 telemetry 레이어와
  일관되어야 한다.
- 모든 측정은 공유 상관 필드를 재사용해 Java, Python, Elastic 타이밍이 같은 턴 위에서
  정렬되게 한다.

## 8. 완료 정의 (이번 PR)

- Stage 0 결론 기록(증거와 함께 가설 수락 또는 기각).
- Stage 1 telemetry 머지 및 턴당 가시화.
- Stage 2 경량화 머지 및 전후 지연/품질 비교.
- Stage 3는 후속 이슈로 명시적 연기.
