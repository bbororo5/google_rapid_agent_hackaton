# LaunchPilot Evaluation Architecture

> 상태: 최소 target architecture
> 상세 감사 근거: [Evaluation System Audit](../reports/evaluation-system-audit.md)

## 1. 목적

이 체계의 목적은 metric을 많이 만드는 것이 아니다. 동일한 사용자 문제와 corpus에서
retrieval/agent architecture를 바꿨을 때 다음을 경험적으로 판단하는 것이다.

- 실제 사용자 문제 해결 능력이 늘었는가?
- 기존 capability regression은 없는가?
- 새 tool의 잠재력과 agent utilization을 구분할 수 있는가?
- 증가한 latency, cost, context, tool call이 정당한가?

과거 문서의 “공식 Retrieval 5대/Generation 4대 metric”은 historical synthetic V3
proxy다. 특히 keyword 기반 faithfulness, 빈 distractor set의 rejection, 단일 gold의
multi-hop coverage, 추정 retrieval latency는 release gate에서 제외한다.

### 1.1 구현 상태

Historical checksum snapshot, Golden V2 candidate selector, V3 priority review queue,
judgment pooling 계약, controlled paired runner는 구현되었다. 그러나 V2 Frozen 후보
64건 중 16건과 Holdout 후보 50건은 사람 검수 대기이며, Holdout 50건은 모두
no-answer 계열이라 분포 대표성이 없다. Human grader calibration, production query
sample, 새 pooled judgments, 실제 V0/V1/V2 live run도 아직 완료되지 않았다.

따라서 현재 구현은 신뢰할 수 있는 실험을 수행하기 위한 기반이지 production
capability gain의 증거가 아니다. artifact별 사용 가능 범위와 다음 작업은
[Eval Portfolio 운영 가이드](../../services/launchpilot-api/evals/portfolio/README.md)에
기록한다.

## 2. Artifact separation

```text
QueryRecord                 어떤 사용자 문제를 풀 것인가
  ↓ query_id
EvalSpecification           성공을 어떻게 정의할 것인가
  ↓ query_id + spec_version
TrialRunResult              특정 system/trial이 실제로 무엇을 했는가
```

코드 계약은
`launchpilot.evaluation.contracts.architecture_eval`에 있다. Query에는 expected tool이나
route를 넣지 않는다. structured/unstructured, lexical/paraphrase, hop, task shape 같은
taxonomy는 slice 설명에만 사용한다.

## 3. 관계별 평가

| 관계 | 최소 metric | architecture decision |
| --- | --- | --- |
| Query → Retrieval | known-relevant Recall@K, MRR/nDCG, judged precision, unjudged@K | retriever/index/chunking 선택 |
| Retrieval → Answer | claim support, citation correctness, unsupported claim rate | context assembly/generation 개선 |
| Query → Answer | task success, required fact coverage, answer relevance, behavior correctness | release gate |
| Reference → Answer | deterministic fact match 또는 calibrated semantic grader | gold가 충분한 task만 보조 사용 |

qrels에 없는 evidence는 `unjudged`다. known irrelevant로 판정하기 전에는 precision
failure로 처리하지 않는다. 새 run의 top result는 pooling review queue에 추가한다.

## 4. Outcome, process, efficiency

Outcome이 primary다.

- Task Success
- Required Fact Coverage
- Groundedness / Citation Support
- Answer Relevance
- Abstention / Clarification Correctness

Retrieval과 agent process는 diagnosis다.

- answer-bearing evidence 확보 여부
- tool sequence, arguments, error, retry, recovery
- redundant/repeated call, premature termination
- forced tool/known-gold evidence condition과 realized agent condition의 차이

Efficiency는 quality와 분리한다.

- E2E 및 retrieval/tool/model latency
- tool calls
- input/output/context token
- cost

Quality gate를 통과한 candidate끼리 cost per successful trial, latency per successful
trial, marginal cost/latency를 비교한다. 임의 weighted total score는 사용하지 않는다.

## 5. Paired architecture experiment

V0/V1/V2는 같은 query, Eval Specification, corpus, model, prompt에서 실행한다. index,
toolset, code version은 의도한 intervention으로 달라질 수 있다.

```bash
launchpilot-compare-eval-runs \
  evals/runs/v0-trials.jsonl \
  evals/runs/v1-trials.jsonl \
  --minimum-trials 3 \
  --pass-rate 0.6666666666666666 \
  --output evals/runs/v0-v1-paired.json
```

위 standalone CLI는 Query/Eval Specification의 leakage mapping을 받지 않으므로 CI를
benchmark-query-conditional로만 해석한다. release용 cluster-aware interval은
`controlled_runner.compare_bundle()`이 QueryRecord의 leakage connected component를
전달하는 경로에서 생성한다.

필수 보고 항목은 다음과 같다.

- Newly Solved / Regression / Net Gain
- Pass→Pass와 Fail→Fail
- required-fact, groundedness, relevance별 win/loss/tie/unscored, scored denominator와 delta
- leakage group과 matched stochastic trial을 반영한 paired hierarchical bootstrap interval,
  independent cluster 수
- answer-bearing evidence 확보율과 동일 cutoff의 known-relevant recall@k
- latency/cost/tool-call delta와 success당 비용
- trial success rate와 all-trials-pass case rate

Optional quality/retrieval delta는 양쪽의 모든 paired trial에 값이 있고 retrieval cutoff가
같을 때만 계산한다. 일부 trial만 채점된 조건부 평균은 각 system의 scored rate와 함께
진단용으로 보여주되 architecture delta로 해석하지 않는다.

## 6. Capability와 utilization

새 tool은 네 조건으로 비교한다.

1. baseline agent-selected
2. new tool forced
3. baseline + new tool forced/fused
4. candidate agent-selected

필요하면 기존 qrels의 known-relevant evidence injection을 추가한다. 이는 불완전한
known gold를 사용하므로 완전한 oracle ceiling이 아니다. forced retrieval은 성공하지만
agent-selected가 실패하면 routing/utilization 문제다. known-gold injection도 실패하면
generation 또는 Eval Specification/grader를 먼저 조사한다.

## 7. Portfolio와 release gate

- Frozen: 안정적인 version comparison
- Holdout: entity/source/template group blind
- Regression: 실제 failure 재발 방지
- Frontier: 새 capability 개발
- Production Sample: 실제 분포와 offline metric 상관 검증

release candidate는 Frozen + Regression에서 non-inferior해야 하고, 고위험 slice의
regression budget, grounding/reliability, cost/latency trade-off를 모두 통과해야 한다.
Frontier 개선만으로 production release를 결정하지 않는다.

## 8. Grader policy

- exact fact/calculation: deterministic code/SQL
- retrieval: IR metric + pooled judgment
- open answer quality: calibrated LLM judge + human audit
- groundedness: claim-evidence mapping + human adjudication sample
- trajectory: deterministic trace diagnostic

LLM judge마다 model/prompt/rubric version을 기록한다. human calibration set에서 agreement,
false-positive/negative, order reversal consistency, repeated-judgment stability를 검증하지
않은 judge는 primary release gate로 사용하지 않는다.
