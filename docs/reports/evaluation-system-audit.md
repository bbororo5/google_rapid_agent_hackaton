# LaunchPilot Evaluation System Audit and Minimal Redesign

> 감사일: 2026-08-27
> 대상: Golden V1/V2/V3, retrieval/generation/agent evaluator, experiment runner,
> 저장된 benchmark 결과
> 결론: 현재 자산은 **합성 환경의 개발 진단**에는 유용하지만, 새 retrieval/agent
> architecture의 production capability gain을 입증하는 단일 benchmark로는 부적합하다.

## 0. Executive decision

현재 가장 큰 문제는 metric이 적어서가 아니다. 서로 다른 세대의 dataset과 runner가
서로 다른 성공 정의를 사용하면서도 모두 `Golden`, `accuracy`, `faithfulness`,
`holdout`이라는 같은 이름을 쓴다는 점이다. 이 상태에서는 Dense나 Graph를 추가한 뒤
점수가 올라가도 다음 중 무엇이 원인인지 분리할 수 없다.

1. retriever 자체의 capability 증가
2. agent의 tool utilization 증가
3. gold 또는 grader가 새 architecture에 더 유리해진 효과
4. corpus, scope, prompt, model, sample이 함께 바뀐 효과
5. 작은 표본과 단일 trial의 우연

따라서 다음 네 가지를 최소 변경으로 채택한다.

- Query, Eval Specification, Trial Run Result를 별도 artifact로 저장한다.
- outcome quality를 primary gate로 두고 retrieval/trajectory는 diagnosis로 둔다.
- 모든 architecture 비교는 동일 case의 paired comparison으로 수행한다.
- evidence pool 밖 문서는 `irrelevant`가 아니라 `unjudged`로 취급하고 review queue로
  보낸다.

기존 V1/V2/V3 파일은 삭제하지 않는다. 재현 가능한 historical fixture로 동결하되,
아래의 유효 범위를 넘어선 production claim에는 사용하지 않는다.

## 1. 감사 범위와 방법

다음 파일을 직접 대조했다.

- Dataset: `evals/golden/golden-v1`, `golden-v2`, `golden-v3`
- Gold: `qrels.jsonl`, `gold_spans.jsonl`, `generation_ground_truth.jsonl`
- Retrieval: experiment runner, V3 harness, `retrieval_stage_evaluator.py`
- Answer: `generation_stage_evaluator.py`, `agent_evaluator.py`
- E2E/ablation: decoupled runner, progressive ablation, N=20 runner
- Results: retrieval, agentic, phase/stress/scale JSON 결과

자동 validation의 `PASS` 여부만 신뢰하지 않고 실제 row 수, label 분포, split group,
grader 조건, runner가 전달하는 scope와 latency를 소스 수준에서 확인했다.

## 2. Dataset audit

### 2.1 세 Golden은 같은 benchmark의 version이 아니다

| 자산 | Query | 주된 목적 | 강점 | 사용 한계 |
| --- | ---: | --- | --- | --- |
| Golden V1 | 600 | structured + document retrieval baseline | 8 query profile, 15 task, 12개 taxonomy 축, leakage group split | 전부 합성, 260건 human review 대기 |
| Golden V2 | 680 | V1 safety/ambiguity 확장 | campaign evidence group을 split 단위로 격리, 340건 자동 검증 | 전부 합성, 340건 human review 대기 |
| Golden V3 | 150 | graph/agent retrieval stress fixture | 1,050 documents, 29 negative, query에 내부 doc key 없음 | 6개 task family, 4 brand, split leakage, gold 불완전 |

V1/V2는 structured, lexical, semantic, mixed, no-answer, ambiguity, adversarial을 함께
다룬다. V3는 121 positive가 사실상 문서 lookup/비교 task에 집중되어 있다. 따라서
V3 점수 상승을 전체 Agentic RAG 문제 공간의 capability gain으로 외삽할 수 없다.

### 2.2 Query source와 representativeness

- V1/V2 corpus와 query는 deterministic synthetic builder에서 생성되었다.
- V3 corpus도 synthetic이며 query는 `raw_generated_cases.json`과 후속 정제 commit에서
  생성되었다.
- production query sample, 실제 marketer 작성 query, expert-authored independent query는
  현재 benchmark에 없다.
- V3 150건은 6개 `analysis_task`에 `30/30/30/30/10/20`으로 분포하고 positive마다
  known relevant evidence가 정확히 1개다.
- V3 brand는 4개뿐이며, 10개 cross-campaign query의 `brand` 값은 `ALL`이다.

따라서 현재 dataset은 운영 분포 추정기가 아니라 controlled synthetic fixture다.
합성 fixture는 deterministic regression에는 적합하지만 production model selection의
대표 표본으로 간주하면 안 된다.

### 2.3 Architecture 및 template bias

긍정적인 부분은 query에 `memo_07`, UUID 같은 내부 answer key가 직접 들어가지 않도록
검사한다는 점이다. 그러나 이것이 architecture independence를 보장하지는 않는다.

- V3 positive는 특정 사건 유형과 문서 위치가 반복되는 lookup template다.
- 동일 campaign의 copy/pacing/brief/video query가 서로 다른 split에 배치된다.
- retrieval runner가 campaign scope를 미리 제공하는 실험과 workspace 전체를 찾는
  실험이 섞여 있다.
- V2 agent evaluator는 `analysis_task`를 expected route로 변환한다. 이는 taxonomy를
  explanatory variable이 아니라 routing truth로 사용한다.

권고: `analysis_task`, `semantic`, `relational` 등의 분류는 slice 분석에만 사용하고
pass/fail 또는 expected first tool을 결정하지 않는다.

### 2.4 Duplicate와 difficulty

V1/V2는 normalized exact duplicate와 taxonomy completeness를 검사한다. V3도 exact
duplicate 및 3-gram leakage를 검사하지만, entity를 제거한 template family의 중복과
semantic near-duplicate를 split 경계에서 검사하지 않는다. V3에는 독립적인 difficulty,
answerability, source cardinality, hop count 분포도 없다.

필요한 최소 slice는 다음뿐이다.

- modality: structured / unstructured / mixed / relational
- lexical need와 paraphrase gap
- entity-centric 여부
- single-hop / multi-hop
- lookup / aggregation / comparison
- single-source / multi-source
- answerable / ambiguous / insufficient-evidence

이 필드들은 route label이 아니라 error analysis용 설명 변수다.

### 2.5 Holdout audit

V1/V2는 `leakage_group_ids`로 campaign evidence group을 하나의 split에 유지한다. 이
설계는 유지할 가치가 있다. 반면 V3는 case ID만 겹치지 않으면 split 독립이라고
판정한다.

- V3 tune에는 C0001~C0030 30개 campaign이 모두 등장한다.
- validation과 holdout에는 각각 24개 campaign이 등장하며 대부분 tune에도 존재한다.
- 동일 campaign 문서와 동일 사건 template가 tune/validation/holdout에 걸쳐 있다.

따라서 V3 `holdout`은 독립 entity/source 일반화 holdout이 아니다. 명칭을 historical
split로 유지하되 release gate에서 제외하고, campaign/source/template group을 함께
묶은 새 holdout을 만들어야 한다.

## 3. Gold audit

### 3.1 Query와 Eval Specification이 결합되어 있다

V1/V2 `cases.jsonl` 한 row에는 query, taxonomy, scope, expected answer, expected facts,
gold evidence, split이 모두 들어 있다. V3는 query와 generation ground truth를 파일로
나누었지만 stable Eval Specification ID와 review provenance가 없다.

이 결합은 query를 재사용하면서 success definition만 개선하기 어렵게 만들고, gold
변경과 query 변경을 동일 dataset version 변경으로 취급하게 한다.

### 3.2 V3 qrels 불일치와 incomplete gold

- `benchmark_audit_report.json`은 qrels 144건이라고 기록한다.
- 현재 `qrels.jsonl`은 121건이며 121 positive case마다 정확히 1건이다.
- relevance grade는 전부 1이므로 graded relevance를 위한 nDCG의 이점이 없다.
- known irrelevant judgment는 0건이다.
- negative 29건은 evidence judgment가 없고 `target=[]`만 존재한다.
- 10개 cross-campaign comparison query도 evidence가 1개뿐이다. 실제 비교 coverage를
  평가하지 못한다.

즉 현재 qrels는 complete answer-bearing evidence set이 아니라 single known-positive
pointer다. Recall@5는 이름과 달리 전체 relevant evidence recall이 아니라
`known target hit@5`로 해석해야 한다.

### 3.3 Unjudged를 failure로 간주하는 위험

새 Dense/Graph retriever가 pool에 없던 더 좋은 문서를 찾을 수 있다. 현재 gold에는
그 문서를 판정할 방법이 없으므로 자동 irrelevant 처리는 새 architecture를 벌주는
pool bias가 된다.

TREC도 큰 corpus에서 완전 판정이 불가능해 여러 run의 상위 결과를 pooling한 뒤
판정한다. 전통 metric이 unjudged를 non-relevant로 취급할 수 있는 전제는 pool이
충분히 다양해 relevance set이 approximately complete하다는 것이다. 현재 V3처럼
single known positive만 있는 경우에는 그 전제가 성립하지 않는다.

권고하는 evidence state는 세 가지다.

- `known_relevant`: information need 또는 required fact를 실제로 지지
- `known_irrelevant`: assessor가 보고 무관하거나 오도한다고 판정
- `unjudged`: 아직 판정하지 않음; 자동 failure가 아니라 review candidate

새 architecture run의 top results를 기존 run과 합쳐 pooled judging을 수행하고 qrels
version을 올린다. Frozen benchmark의 과거 score는 당시 qrels version과 함께 보존한다.

### 3.4 Generation gold의 blind spot

- `expected_numbers`는 단순 문자열 포함으로 평가한다. `15%`가 있으면 잘못된 추가
  수치나 단위를 말해도 numeric exactness를 통과할 수 있다.
- causal triad는 각 component에서 토큰 하나만 answer에 있어도 해당 hop이 있다고
  본다. 인과 관계나 evidence entailment를 평가하지 않는다.
- `faithfulness_passed`는 causal token 일부 + 숫자 포함 여부다. retrieved evidence와
  claim의 관계를 확인하지 않는다.
- negative answer는 6개 한국어 phrase 중 하나가 있으면 통과한다. 그 문장 뒤에
  fabricated claim이 있어도 탐지하지 못한다.
- positive마다 expected document UUID가 1개뿐이어서 alternative valid citation을
  citation error로 만들 수 있다.

이 metric은 lexical conformance diagnostic으로는 쓸 수 있지만 groundedness,
faithfulness, open-ended correctness라는 primary 이름으로 보고하면 안 된다.

## 4. Metric and grader audit

### 4.1 관계별 평가 현황

| 관계 | 현재 상태 | 판정 |
| --- | --- | --- |
| Query → Retrieval | V1/V2 runner의 exact ref/span Recall, MRR, nDCG는 유효 | 유지하되 incomplete qrels 표기 |
| Retrieval → Answer | claim-evidence entailment 없음 | 신규 추가 필요 |
| Query → Answer | V3 required-fact/task success 불완전 | primary grader 재설계 필요 |
| Reference → Answer | canonical string/keyword proxy | deterministic fact에만 제한 |

RAGAS도 retrieval context의 relevance, answer의 faithfulness, answer quality를 별도
관계로 본다. 본 프로젝트는 모든 metric을 도입할 필요는 없지만 관계를 섞지는 않아야
한다.

### 4.2 Retrieval metric 구현 문제

감사 당시 `retrieval_stage_evaluator.py`와 decoupled runner에는 다음 문제가 있었다.

- V3 positive는 target 1개이므로 hit rate, recall, multi-hop coverage가 동일하다.
- `multihop_coverage = recall`로 직접 대입한다. 실제 hop 또는 dependency를 평가하지
  않는다.
- runner가 distractor set을 항상 빈 set으로 전달해 distractor rejection은 항상 1이다.
- negative case는 retrieval result가 있어도 hit/recall/MRR/multihop를 모두 1로 둔다.
- ID substring matching은 짧거나 prefix가 같은 reference에서 false match 위험이 있다.
- retrieval latency를 E2E latency의 절반(`e2e_dur * 500`)으로 추정한다.
- validation 30건 중 앞의 15건만 실행한다.
- 모든 case에서 C0001 reader/scope를 사용해 case별 campaign 조건을 보존하지 않는다.

이번 변경에서 negative/unjudged semantics, single-target multi-hop 제외, 실제 validation
case 수와 case별 campaign scope, 추정 retrieval latency 제거를 수정했다. 저장된 과거
결과는 수정 전 evaluator의 산출물이므로 historical proxy로 남는다.

V1/V2 experiment metric 구현은 exact document ref와 span overlap을 사용하므로 더
신뢰할 수 있다. 단, unjudged를 0 gain으로 처리하고 denominator를 고정하므로 qrels
completeness를 함께 보고해야 한다.

### 4.3 Agent grader 구현 문제

`GoldenAgentEvaluator`에서 positive answer는 final text가 비어 있지 않으면 pass다.
route correctness는 별도 계산되지만 positive pass 조건에 포함되지 않는다. 저장된
V2 agent benchmark의 680/680은 실제 answer correctness 100%가 아니다. 또한 runner는
실제 production model 대신 규칙 기반 fake model을 사용한다. 이 결과는 plumbing
smoke test로만 유지해야 한다.

V3 ablation grader도 UUID/title 또는 action keyword 두 개를 찾으면
`GROUNDED_FAITHFUL`로 표시한다. 이는 groundedness가 아니라 surface match다.

### 4.4 Grader portfolio

| 평가 대상 | Primary grader | 보조 grader | 이유 |
| --- | --- | --- | --- |
| exact fact/calculation | deterministic code/SQL | human spot check | 값·단위·기간을 완전 비교 가능 |
| retrieval rank | IR metric over judged pool | pooled human judgment | architecture-neutral하고 재현 가능 |
| required fact coverage | atomic fact checker | calibrated LLM + human | open wording 허용, 누락 탐지 |
| groundedness/citation | claim-evidence mapping/NLI | human adjudication | citation 존재와 claim support는 다름 |
| answer relevance/completeness | rubric LLM judge | human calibration set | open-ended semantics 필요 |
| abstention/clarification | answerability label + contradiction check | human | phrase match만으로 부족 |
| trajectory | deterministic trace rules | LLM summary | tool/order는 diagnosis이며 outcome과 분리 |

LLM judge는 calibration set에서 human agreement, false-positive/negative, prompt/repetition
stability를 측정한 뒤 사용한다. generator와 같은 model family 하나에만 의존하지 않고,
pairwise judge에서는 answer 순서를 뒤집어 position consistency를 확인한다.

## 5. Experiment audit

### 5.1 통제된 실험과 통제되지 않은 실험

V1 retrieval matrix는 같은 corpus/query/qrels에서 chunker/retriever 조합을 바꾸므로
가장 잘 통제된 실험이다. 다만 campaign pre-filter와 synthetic concept-hash dense라는
제약 때문에 운영 성능으로 외삽할 수 없다.

Phase 1/2/3 agent ablation은 model call, graph, routing, reranker, tool availability가
함께 바뀌며 run manifest에 model/prompt/corpus/commit/seed가 없다. 저장 결과만으로
reranker 또는 Graph의 단독 causal effect를 식별할 수 없다.

### 5.2 N=20 결과는 통계적으로 powered되지 않았다

`scale_benchmark_n20_phase2_vs_phase3.py`는 comparison case prefix를 잘못 찾아 실제로
각 version 18건만 실행했다. summary는 여전히 20으로 나누어 80%, 90%를 기록한다.
power analysis, confidence interval, paired significance test도 없다. 따라서 파일명과
출력의 `STATISTICALLY POWERED N=20` 주장은 철회해야 한다.

### 5.3 Paired analysis 부재

현재 저장 결과는 aggregate accuracy와 latency 중심이다. 동일 query에서 다음 전이를
직접 집계하지 않는다.

- Fail → Pass: Newly Solved
- Pass → Fail: Regression
- Pass → Pass: quality/groundedness/efficiency delta
- Fail → Fail: unresolved

평균만 보면 regression이 newly solved에 가려질 수 있다. architecture 변경은 case별
paired result를 primary comparison unit으로 사용해야 한다. continuous quality delta에는
paired bootstrap confidence interval 또는 paired randomization test를 사용하고 effect
size도 함께 보고한다.

### 5.4 Stochasticity와 reliability

현재 중요한 agent benchmark는 query당 대부분 1 trial이다. 평균 상승과 reliability
상승을 구분할 수 없다. release candidate는 최소 3 trials, high-risk/unstable slice는
5 trials를 권장한다. query별 success rate와 cost/latency variance를 기록하고, release
gate에는 mean뿐 아니라 lower confidence bound 또는 최소 trial pass rate를 둔다.

### 5.5 Efficiency와 observability

현재 latency와 tool name 일부는 남지만 다음이 일관되게 없다.

- 실제 retrieval latency와 E2E latency 분리
- input/output/reasoning token
- retrieved context token/bytes
- model/tool별 cost
- tool arguments, status, error, retry, recovery
- corpus/index/model/prompt/toolset/commit version

OpenTelemetry GenAI convention도 agent invocation 아래 model call과 tool execution span,
token usage를 별도로 기록하는 방향이다. 본 프로젝트는 vendor-specific framework를 더
도입하기보다 현재 trace에 위 최소 필드를 추가하면 충분하다.

## 6. Minimal target model

### 6.1 Artifact separation

```text
QueryRecord
  query_id, text, source, portfolio, explanatory_slices, leakage_group_ids

EvalSpecification
  spec_id, query_id, answerability, required_facts, expected_behaviors,
  evidence_judgments, reviewer/provenance, spec_version

TrialRunResult
  run_id, system_version, query_id, spec_version, trial_id,
  retrieved_refs, answer, outcome_scores, tool_trace, latency/tokens/cost,
  corpus/index/model/prompt/toolset/commit versions
```

`QueryRecord`에는 expected tool 또는 route를 넣지 않는다. 특정 tool을 강제하는 oracle
experiment는 Eval Specification이 아니라 experiment intervention으로 기록한다.

### 6.2 Primary와 diagnostic metric

Release gate의 최소 primary metric은 다섯 개다.

1. Task Success
2. Required Fact Coverage
3. Groundedness / Citation Support
4. Answer Relevance
5. Abstention 또는 Clarification Correctness

Retrieval metric과 agent process metric은 primary outcome이 실패한 이유를 찾는
diagnostic이다. 단, retrieval component를 독립 배포하거나 index를 선택하는 실험에서는
IR metric이 해당 component experiment의 primary가 될 수 있다.

### 6.3 Quality-first efficiency comparison

임의 weighted single score는 만들지 않는다.

1. quality non-inferiority와 regression budget을 먼저 통과시킨다.
2. 통과한 candidate끼리 cost per successful query와 latency per successful query를
   비교한다.
3. marginal quality gain, marginal cost, marginal latency를 함께 보고한다.

### 6.4 Capability ceiling과 utilization gap

새 tool마다 같은 query/spec/corpus에서 다음 intervention을 실행한다.

- baseline agent-selected
- new tool forced
- baseline + new tool forced/fused
- oracle evidence injected generation
- candidate agent-selected

이를 통해 다음 failure location을 분리한다.

- forced retrieval도 실패: tool/index/representation 문제
- forced retrieval 성공, agent-selected 실패: routing/utilization 문제
- evidence injection 성공, normal generation 실패: retrieval 또는 context assembly 문제
- evidence injection도 실패: generation/spec/grader 문제

`Capability Ceiling - Agent Realized Performance`를 utilization gap으로 보고하되, oracle
condition은 production score와 섞지 않는다.

## 7. Eval portfolio

| Portfolio | 목적 | 변경 정책 | 현재 자산의 배치 |
| --- | --- | --- | --- |
| Frozen Benchmark | version 간 공정 비교 | query/spec/qrels version 고정 | human-reviewed V2 subset부터 시작 |
| Holdout | eval/routing overfit 탐지 | entity/source/template group blind | 새로 생성 필요 |
| Regression | 실제 failure 재발 방지 | failure 발견 시 성장 | V1/V2 safety cases 일부 이관 |
| Frontier | 새 capability hill-climbing | 자주 성장, release claim 제한 | V3 graph/multi-hop cases 정비 후 이관 |
| Production Sample | 실제 분포/quality 상관 | 주기적 time-window sampling | 현재 없음 |

Stable과 growing을 하나의 파일에서 해결하지 않는다. Frozen/holdout은 versioned하고,
regression/frontier/production sample은 별도 cadence로 성장시킨다.

## 8. A–E disposition

### A. 그대로 유지할 것

- V1/V2의 stable corpus refs, span 기반 document judgment: chunker 독립적인 gold다.
- V1/V2의 `leakage_group_ids` split: entity/evidence leakage를 막는 올바른 방식이다.
- deterministic formula validation: numeric fact의 가장 신뢰도 높은 grader다.
- retrieval experiment manifest와 case-level result: paired 분석으로 확장하기 좋다.
- synthetic fixtures: 빠르고 재현 가능한 regression/component test로 가치가 있다.
- retrieval/generation 분리라는 방향: 관계별 평가로 더 세분화하면 된다.

### B. 수정해야 할 것

- Golden V3: holdout 재분할, cross-campaign gold 보완, review provenance와 answerability 추가
- qrels: known relevant만 저장하지 말고 judged irrelevant와 unjudged 상태/coverage 기록
- agent pass criteria: non-empty/keyword match에서 required facts + groundedness로 변경
- experiment result: run manifest, trial ID, per-case outcome/process/efficiency 기록
- latency: 실제 span에서 retrieval/tool/model/E2E를 각각 측정
- LLM judge: human calibration set과 judge version/stability 기록
- documentation: `faithfulness`, `official`, `statistically powered` 같은 검증되지 않은
  claim을 proxy/smoke-test로 정정

### C. 제거하거나 primary에서 강등할 것

- V3의 `hit_rate`, `recall`, `multihop_coverage` 동시 primary 보고: 현재 모두 같은 값
- 빈 distractor set에서 계산한 distractor rejection
- E2E latency의 절반을 retrieval latency로 간주하는 값
- keyword 두 개를 grounded faithfulness라고 부르는 grader
- fake model의 680/680을 agent accuracy라고 부르는 결과
- route label mismatch를 outcome failure로 보는 규칙
- quality/cost/latency 임의 weighted single score

Historical artifact는 삭제하지 않고 `legacy/proxy`로 명시한다.

### D. 새로 추가해야 할 것

- Query/EvalSpec/TrialRunResult 중립 schema
- evidence judgment state와 pooling review queue
- required atomic facts 및 expected behavior
- per-case paired transition + win/loss/tie + bootstrap interval
- query × trial reliability와 variance
- tool trace, retry/recovery/error, token/context/cost observability
- oracle/forced-tool counterfactual matrix
- production sample과 grader calibration sample

### E. 즉시 해야 할 작업

1. 현재 V1/V2/V3와 결과를 historical snapshot으로 동결한다.
2. 본 감사에서 확인한 invalid claim과 runner defect를 release 문서에서 정정한다.
3. Query/EvalSpec/TrialRunResult schema를 도입한다.
4. V2에서 자동 검증 가능한 case와 고가치 safety case를 선별해 Frozen v0를 만든다.
5. V3 10개 comparison case와 29개 negative부터 human review한다.
6. pooled top results에 known relevant/irrelevant 판정을 추가하고 unjudged rate를 보고한다.
7. campaign/source/template group 기반 새 holdout을 만든다.
8. V0/V1/V2를 동일 corpus/model/prompt 조건과 query당 3 trials로 다시 실행한다.
9. paired transition, slice delta, cost/latency per success를 생성한다.
10. forced tool/oracle evidence 실험으로 capability와 utilization을 분리한다.
11. automated grader 100~200건 calibration sample을 human 2인 판정과 비교한다.
12. production query sample을 추가한 뒤 offline metric과 human task success의 상관을
    분기별로 재검증한다.

## 9. Release decision rule

새 architecture는 다음을 모두 만족할 때만 채택한다.

- Frozen + Regression에서 candidate task success가 baseline에 non-inferior
- 고위험 slice의 regression이 사전 합의한 budget 이내
- Newly Solved가 Regression보다 많고 paired quality delta가 실질적으로 의미 있음
- groundedness/abstention reliability가 악화되지 않음
- cost/latency 증가가 새로 해결한 query와 production priority로 정당화됨
- 결과가 최소 trial 수와 run manifest를 갖춰 재현 가능함

평균 score 1개가 아니라 이 decision record가 architecture 채택의 산출물이다.

## 10. 근거가 된 평가 철학과 자료

- TREC test collection은 topic, corpus, qrels, run을 분리하고 pooling으로 relevance
  judgment를 확장한다: [NIST How To TREC](https://trec.nist.gov/howto.html),
  [TREC qrels format](https://trec.nist.gov/data/qrels_eng/)
- 불완전 pool은 새로운 retrieval approach의 top result를 과소평가할 수 있다:
  [TREC 2022 Deep Learning Track analysis](https://trec.nist.gov/pubs/trec31/papers/UAmsterdam.D.pdf)
- RAG는 retrieval relevance, answer faithfulness, answer quality를 분리해야 한다:
  [RAGAS paper](https://arxiv.org/abs/2309.15217)
- 동일 topic에서 system을 비교할 때 paired test와 effect size가 필요하다:
  [Smucker, Allan, Carterette 2007](https://doi.org/10.1145/1321440.1321528)
- LLM judge는 position, authority, presentation bias 등에 취약하므로 human calibration이
  필요하다: [Chen et al., EMNLP 2024](https://aclanthology.org/2024.emnlp-main.474/)
- agent trace는 outcome을 대체하지 않지만 failure diagnosis에 필요하다:
  [AgentDiagnose, EMNLP 2025](https://aclanthology.org/2025.emnlp-demos.15/)
- production trace는 agent/model/tool span과 token usage를 분리 기록한다:
  [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)

## 11. 이 감사의 한계

- 실제 production query와 human judgment가 없어 production representativeness 자체를
  실측하지 못했다.
- 저장된 결과에 model/prompt/commit metadata가 없어 과거 run을 완전히 재구성하지
  못했다.
- 이번 감사는 local artifact와 source code를 대상으로 했으며 운영 telemetry backend의
  실제 span payload는 포함하지 않았다.

이 한계는 더 많은 taxonomy나 metric으로 해결되지 않는다. production sample,
human calibration, versioned run manifest를 추가해야 해결된다.
