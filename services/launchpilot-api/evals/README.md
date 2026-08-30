# LaunchPilot Eval: 문제에서 답까지

Eval은 현재 SQL/BM25/Dense/Graph 구현을 시험하는 부속물이 아니다. 시스템이 앞으로
어떤 구조로 바뀌더라도 **같은 문제를 더 잘 풀게 되었는지** 관찰하기 위한 독립된
실험 경계다.

## 1. 한 장의 멘탈 모델

```text
사전 정의                         실행                         사후 판단

World ──┐
        ├─ Problem ────────────> System under test ───────> Answer
Context ┘   "무엇을 풀까?"       (어떤 구조도 가능)           + Evidence
                                                               + Trace
                                                               + Telemetry
Eval Specification ─────────────────────────────────────────> Judgment
"무엇이면 성공인가?"                (시스템에는 비공개)         "성공했나?"
```

기본 단위는 tool query가 아니라 `ProblemRecord`다. 사용자 발화가 불완전하거나 모순될
수 있으므로 problem은 발화뿐 아니라 사전에 사용자에게 주어진 context와 실제
information need를 함께 식별한다. 올바른 답은 사실을 말하는 것일 수도, 재질문하거나
근거 부족을 밝히는 것일 수도 있다.

평가는 네 층을 섞지 않는다.

1. **Problem** — 어떤 사용자 문제를 재현하는가.
2. **Answer** — 그 encounter가 성공했는가. 이것이 primary outcome이다.
3. **Process** — evidence와 tool trajectory가 성공·실패를 어떻게 만들었는가. 진단용이다.
4. **Operational quality** — latency, token, cost, reliability 같은 시스템 대가다.

Process나 비용이 좋아도 틀린 답을 정당화하지 않는다. 먼저 quality constraint를
통과한 시스템끼리 운영 효율을 비교한다.

## 2. 정문 디렉터리

```text
evals/
├── datasets/                         # 현재 평가 입력의 유일한 정문
│   ├── README.md
│   ├── registry.json
│   └── marketing-ops-task-v1/
│       ├── manifest.json
│       ├── world/manifest.json
│       ├── problems/problems.jsonl
│       ├── specifications/eval-specifications.jsonl
│       ├── judgments/evidence-assessments.jsonl
│       └── references/answer-examples.jsonl
├── golden/                           # 과거 fixture; V1/V2는 archive 전용
├── portfolio/                        # historical snapshot과 검수/pooling 자료
├── migrate_v3_to_task_dataset.py     # V3 provenance를 보존한 일회성 이관기
└── validate_task_dataset.py          # 구조·참조·hash·release blocker 검사

src/launchpilot/evaluation/
├── contracts/architecture_eval.py   # Problem/Spec/Run Result 타입 계약
├── task_dataset.py                  # canonical dataset loader와 검증
├── task_dataset_cli.py              # readiness report
├── controlled_runner.py             # paired, multi-trial 실행 경계
├── judging/                          # 사전 adjudication + 사후 answer grading
│   ├── gemini_client.py              # Gemini 3.7 Flash/medium adapter
│   ├── spec_adjudicator.py           # 두 번의 독립 spec 판정
│   ├── task_grader.py                # trial 원자 판정
│   ├── policy.py                     # 결정론적 score/task_success 집계
│   └── materialize.py                # 원본 불변 파생 snapshot 생성
└── harness_v3.py                    # 과거 V3 재현 전용; release gate 아님

tests/
├── test_task_dataset.py             # artifact 간 참조와 불변식
├── test_committed_task_dataset.py   # 저장소에 커밋된 dataset의 실제 상태
├── test_architecture_eval_contracts.py
└── test_controlled_eval_runner.py   # gold redaction, pairing, fingerprint 고정
```

`evals/`는 평가 데이터와 실행 진입점, `src/.../evaluation/`은 재사용 가능한 계약과
실행 코드, `tests/`는 그 경계가 깨지지 않는지를 검사한다. 세 디렉터리가 서로 다른
평가 체계를 뜻하지 않는다.

## 3. Dataset 파일을 읽는 순서

### `manifest.json`

dataset의 신분증이다. dataset/world version, row 수, lifecycle, human review 상태와
release 가능 여부를 고정한다. 동일 이름의 파일을 조용히 바꾸지 않고 새 version을
만드는 기준이다.

### `world/manifest.json`

모든 후보 시스템이 마주할 동일한 현실 snapshot을 가리킨다. 문서와 observation의
경로·hash·record count를 기록한다. BM25 index, embedding, graph projection은 현실이
아니라 시스템의 representation이므로 넣지 않는다.

### `problems/problems.jsonl`

한 줄이 하나의 사용자 encounter다.

```json
{
  "problem_id": "v3-pos-001",
  "user_utterance": "이 캠페인의 전환 하락 원인이 뭐야?",
  "information_need": "현재 캠페인의 전환 하락 근거와 원인을 설명한다.",
  "world_id": "synthetic-marketing-ops-v3",
  "supplied_context": [{"key": "active_campaign", "value": "C0001"}],
  "characteristics": {"modalities": ["unstructured"], "task_shape": "lookup"}
}
```

`user_utterance`와 `supplied_context`는 시스템에 보인다. `information_need`와
`characteristics`는 평가·분석 의미를 설명하지만 expected tool이나 route가 아니다.

### `specifications/eval-specifications.jsonl`

같은 `problem_id`가 무엇을 만족해야 성공인지 정의한다.

```json
{
  "problem_id": "v3-pos-001",
  "answerability": "answerable",
  "required_facts": [{"fact_id": "cause", "description": "하락 원인"}],
  "expected_behaviors": ["answer"],
  "review_status": "needs_review"
}
```

이 파일은 grader에만 보인다. “Dense를 호출하라” 같은 구현 지시를 넣지 않는다.
spec을 개선해도 problem 자체는 바뀌지 않으며, spec version과 provenance를 별도로
추적한다.

### `judgments/evidence-assessments.jsonl`

사람 또는 명시된 이관 절차가 실제로 판정한 evidence만 저장한다. 각 판정은 어떤
required fact를 지지하는지도 연결할 수 있다.

```json
{"problem_id":"v3-pos-001","assessment":{"evidence_ref":"memo-123","judgment":"known_relevant","relevance_grade":3,"supports_fact_ids":["cause"]}}
```

파일에 없는 문서는 `unjudged`다. 새 retriever가 찾은 evidence를 자동으로 irrelevant로
취급하지 않는다. 비교할 retriever의 top-k를 pooling하고 명시된 assessor가 판정해
judgment version을 확장한다. 현재 프로젝트는 human review를 운영하지 않으므로 LLM
판정은 반드시 `machine_adjudicated`로 표기하며 human review로 가장하지 않는다.

### `references/answer-examples.jsonl`

가능한 답변 예시다. required facts를 이해하거나 grader를 보조할 수 있지만 정답 문장
ontology는 아니다. 현재 이관본은 모두 `grading_authority=false`이므로 자동 채점의
절대 기준으로 사용하지 않는다.

## 4. 여섯 관계와 저장 위치

| 관찰 관계 | 주된 근거 | 판단 목적 |
| --- | --- | --- |
| World → Evidence | world provenance, evidence judgment | evidence가 실제 현실을 나타내는가 |
| Problem → Evidence | qrels/pool, retrieval diagnostics | 필요한 근거를 확보했는가 |
| Evidence → Answer | claim support, citation mapping | 답의 주장이 가져온 근거에 의해 지지되는가 |
| Problem → Answer | required facts/behavior | 사용자 문제를 실제로 해결했는가 |
| Reference → Answer | 제한된 reference/calibrated grader | 닫힌 정답이 있는 경우 일치하는가 |
| Trial → Operation | trace/telemetry | 성공의 비용·지연·안정성은 어떤가 |

이 관계들을 하나의 RAG score로 합치지 않는다. Problem → Answer가 release의 중심이고,
나머지는 실패 원인과 architecture trade-off를 설명한다.

## 5. 실행 경계

`run_controlled_task_dataset()`은 plan의 dataset ID/version/fingerprint가 실제 로드한
dataset과 일치해야만 실행한다. 시스템 executor에는 발화, 언어, world ID, supplied
context만 전달한다. required facts, qrels, taxonomy는 grader 쪽에 남아 evaluator
leakage를 막는다.

V0/V1/V2 같은 이름은 dataset 세대가 아니라 **동일 problem/spec/world에서 비교하는
시스템 조건**을 뜻해야 한다. query × multiple trials를 같은 seed block으로 paired
실행하고 다음을 별도로 보고한다.

- outcome: Newly Solved, Regression, Net Gain, fact coverage, groundedness
- process: evidence 확보, routing, recovery, redundant call, failure stage
- reliability: trial success rate와 분산
- operations: latency, token, context size, tool call, cost와 success당 비용

## 6. 현재 데이터셋의 정확한 지위

`marketing-ops-task-v1`은 Golden V3 합성 fixture를 새 계약에 옮긴 **frontier draft**다.
V1/V2 데이터는 사용하지 않았다. 현재 150개 problem과 specification, 121개
known-relevant seed, 150개 non-authoritative answer example이 있다.

원본 draft는 다음 이유로 release benchmark가 아니다.

- 150개 specification 모두 `needs_review`
- production-sourced problem 0개
- 기존 qrels는 완전한 relevance set이 아니라 known-positive seed
- comparison problem의 evidence coverage가 불완전

검증 명령:

```bash
.venv/bin/python evals/validate_task_dataset.py
```

현재 검증 결과가 실패가 아니라 `release_ready=false`와 blocker 목록을 출력하는 것이
정상이다.

`marketing-ops-task-2026-08-judge-ready`는 이 원본을 Gemini 3.7 Flash
thinking=medium으로 두 번씩 독립 판정한 파생 snapshot이다. answerable 121건 중 111건은
accept/accept로 승격됐고 comparison 10건은 reject/reject였다. insufficient-evidence
29건은 empty qrels가 부재를 증명하지 못하므로 미승격 상태다. 따라서 이 snapshot도
`release_ready=false`이며, accepted answerable task를 대상으로 grader와 controlled
runner를 개발하는 용도다.

## 7. Judge 경계

```text
Pre-run:  Problem + candidate Spec + known-positive Evidence
                         │
                         ├─ Gemini pass 1 ─┐
                         └─ Gemini pass 2 ─┴─ consensus ─> derived Spec snapshot

Post-run: Problem + accepted Spec + Answer + actually retrieved Evidence
                         │
                         └─ Gemini atomic verdicts
                              ├─ fact entailment
                              ├─ claim support
                              ├─ behavior
                              └─ relevance
                                     │
                          deterministic policy
                                     └─ outcome scores/task_success
```

Judge는 `task_success`를 직접 출력하지 않는다. model verdict와 최종 집계를 분리해 prompt
변경이 score 의미를 몰래 바꾸지 못하게 한다. 시스템 latency/token/cost와 judge
latency/token/cost도 별도 필드다. provider/schema 오류는 `grading_failed`이며 시스템
실패나 task failure로 계산하지 않는다. 자세한 실행법과 제약은
[`JUDGE.md`](JUDGE.md)에 있다.

## 8. 다음 admission 순서

1. comparison 10건의 required facts와 양쪽 evidence seed를 다시 작성한다.
2. negative 29건은 pooled/exhaustive-world 절차로 부재를 검증한다.
3. 비식별 production encounter를 수집해 problem distribution과 missing slice를 본다.
4. entity/source/template leakage group 기준으로 Frozen과 blind Holdout을 만든다.
5. human review가 불가능하므로 mutation/consistency set과 deterministic invariant로 judge를
   지속 qualification하고, 이를 human calibration의 대체물이라고 과장하지 않는다.
6. 검수된 동일 dataset으로 baseline/forced-tool/agent-selected 조건을 paired rerun한다.
7. quality non-inferiority를 먼저 확인한 뒤 marginal cost와 latency를 비교한다.

상세한 평가 철학은 [Evaluation Architecture](../../../docs/architecture/evaluation-framework.md),
기존 체계에 대한 근거는 [Evaluation System Audit](../../../docs/reports/evaluation-system-audit.md)를
참조한다.
