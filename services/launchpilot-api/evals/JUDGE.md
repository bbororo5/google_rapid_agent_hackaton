# Gemini Eval Judge handoff

## 책임 경계

Judge는 에이전트의 일부가 아니다. 에이전트가 사용하는 `LLM_MODEL`, tool, prompt,
retrieval route와 독립된 evaluation adapter이며 다음 두 시점에만 동작한다.

```text
                   evaluation-only Gemini 3.7 Flash / medium

Before run                                               After run
Problem ─┐                                               Problem ─┐
Spec ────┼─> two-pass spec adjudication                  Spec ────┼─> atomic grading
Evidence ┘        │                                      Answer ──┤
                  └─> machine-adjudicated Spec           Evidence ┘
                                                               │
                                             deterministic aggregation
                                                               └─> Outcome
```

사전 판정은 problem과 success specification이 맞는지, required facts가 supplied
known-positive evidence에 의해 지지되는지, tool-independent인지 본다. 두 pass가 모두
accept해야 승격한다. qrels가 비어 있다는 사실은 evidence 부재의 증명이 아니므로
insufficient-evidence spec은 현재 절차로 승인하지 않는다.

사후 채점에서 model은 fact entailment, answer claim support, behavior, relevance만
구조화해 반환한다. `policy.py`가 fact coverage, groundedness, answer relevance와 최종
`task_success`를 계산한다. reference answer는 grader 입력에 넣지 않으며, 실제 trial이
가져온 canonical evidence만 grounding 근거로 사용한다.

## 물리 구조

```text
evals/rubrics/
├─ spec-adjudication-v1.yaml       # 사전 판정 prompt contract
└─ task-answer-v1.yaml             # 사후 채점 prompt contract

src/launchpilot/evaluation/judging/
├─ config.py                       # EVAL_JUDGE_*; 모델/medium 고정
├─ contracts.py                    # structured verdict schemas
├─ gemini_client.py                # Vertex generateContent, retry, telemetry
├─ world_evidence.py               # hash-verified canonical evidence resolution
├─ spec_adjudicator.py             # two-pass consensus
├─ materialize.py                  # append-only derived dataset
├─ task_grader.py                  # TrialGrader implementation
├─ policy.py                       # deterministic aggregation + IR diagnostics
└─ cli.py                          # preflight/adjudicate/checkpoint-resume
```

## 실행

`.env`의 `GOOGLE_CLOUD_PROJECT`와 ADC가 준비되어 있어야 한다. judge 설정은 에이전트
모델 설정과 분리된다.

```bash
set -a; source .env; set +a

.venv/bin/python -m launchpilot.evaluation.judging.cli preflight

.venv/bin/python -m launchpilot.evaluation.judging.cli adjudicate \
  --dataset-root evals/datasets/marketing-ops-task-v1 \
  --output-root evals/datasets/marketing-ops-task-2026-08-judge-ready \
  --rubric evals/rubrics/spec-adjudication-v1.yaml \
  --checkpoint evals/runs/spec-adjudication-2026-08.checkpoint.jsonl \
  --confirm-live-calls
```

명령은 원본 또는 기존 output을 덮어쓰지 않는다. checkpoint는 source dataset
fingerprint에 결속되며 항목별로 append된다. live 비용이 발생하므로 명시적 확인 flag가
없으면 adjudication을 거부한다.

## 현재 qualification 결과

- live preflight: 성공 (`gemini-3.7-flash`, thinking `medium`)
- structured spec calls: 242회 성공, retry 7회
- two-pass agreement: accept/accept 111, reject/reject 10, disagreement 0
- unadjudicated: insufficient-evidence 29
- estimated judge cost: 약 $0.82 (2026-08-30 단가 가정)
- repository tests: grader adapter, schema retry, evidence isolation, deterministic policy,
  checkpoint binding, materialization, controlled-run failure separation을 포함

상세 수치는 파생 dataset의 `adjudication/run-summary.json`에 고정되어 있다. 이 결과는
integration qualification이지 human preference calibration이 아니다. 따라서 다음 release
gate는 comparison gold repair, negative absence protocol, production encounter 추가,
mutation/consistency qualification이다.
