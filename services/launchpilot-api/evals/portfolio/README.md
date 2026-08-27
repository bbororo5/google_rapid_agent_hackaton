# Eval Portfolio 운영 가이드

> 상태: 평가 재설계의 데이터·실행 기반은 구현되었지만 release benchmark는 아직
> 준비 중이다. 이 문서는 무엇이 실제로 생성되었고 무엇이 아직 증명되지 않았는지를
> 구분한다.

이 포트폴리오의 목적은 같은 문제 공간에서 retrieval/agent architecture를 바꿀 때
capability gain, regression, reliability, cost를 paired experiment로 판단하는 것이다.
기존 Golden V1~V3와 과거 결과를 폐기하거나 새 기준으로 소급 해석하지 않는다.
기존 파일은 historical fixture로 보존하고, 새 Query/Eval Specification/Trial Result
계약으로 앞으로의 실험을 실행한다.

상세한 감사 근거와 평가 철학은
[Evaluation System Audit](../../../../docs/reports/evaluation-system-audit.md), target
architecture는
[Evaluation Architecture](../../../../docs/architecture/evaluation-framework.md)를
참조한다.

## 1. 현재 상태와 사용 가능 범위

| 자산 | 현재 상태 | 지금 가능한 사용 | 아직 하면 안 되는 주장 |
| --- | --- | --- | --- |
| Historical snapshot | 50개 파일의 경로·크기·SHA-256 동결 완료 | 과거 dataset/result drift 탐지, 재현성 기준점 | 과거 proxy score가 production quality를 입증한다는 주장 |
| Golden V2 Frozen candidate | 64건 선별: 48건 `ready`, 16건 `pending_human_review` | 48건의 자동 검증 가능한 제한적 regression/component 평가 | 64건 전체가 human-validated Frozen이라는 주장 |
| Golden V2 Holdout candidate | 50건, 전부 no-answer 계열이며 human review 대기 | split/leakage 문제를 드러내는 audit artifact | 전체 문제 분포를 대표하는 blind Holdout이라는 주장 |
| Golden V3 priority queue | 39건: negative 29건, comparison 10건 | 전문가 검수 작업의 우선순위와 lineage 관리 | queue가 새 relevance/answer gold를 이미 확정했다는 주장 |
| Judgment pooling | schema, conflict detection, versioned merge 구현 | 여러 retriever의 top-k를 합쳐 판정 대기 pool 생성 | qrels에 없는 결과를 irrelevant로 처리하거나 pool이 완성됐다는 주장 |
| Controlled runner | paired schedule, provenance, failure semantics, 비교 보고 구현 | 검수된 spec과 실제 adapter/grader가 준비된 뒤 V0/V1/V2 실행 | 현재 저장소가 실제 V0/V1/V2 capability gain을 이미 입증했다는 주장 |
| Human grader calibration | 미완료 | calibration protocol 설계 | automated judge를 primary release truth로 사용 |
| Production sample | 없음 | 수집·비식별화·검수 기준 설계 | synthetic benchmark가 production 분포를 대표한다는 주장 |
| Costly live run | 미실행 | 실행 전 조건·비용을 검토 | unit test/smoke run을 production experiment로 보고 |

여기서 `candidate`는 의도적인 표현이다. 선별되었다는 사실은 사람 검수가 끝났거나
운영 분포를 대표한다는 뜻이 아니다.

## 2. Artifact 구조와 소유권

```text
evals/portfolio/
├─ README.md
├─ historical/
│  └─ pre-redesign-historical-v1.json
├─ golden-v2-portfolio-v0/
│  ├─ selection-manifest.json
│  ├─ frozen-candidate/
│  │  ├─ queries.jsonl
│  │  ├─ eval-specifications.jsonl
│  │  └─ manifest.json
│  └─ holdout-candidate/
│     ├─ queries.jsonl
│     ├─ eval-specifications.jsonl
│     └─ manifest.json
└─ review/
   ├─ v3-priority-review.jsonl
   └─ v3-priority-review.manifest.json
```

- `queries.jsonl`: 사용자가 해결하려는 문제와 분석용 characteristics만 저장한다.
- `eval-specifications.jsonl`: answerability, required facts, expected behavior, 현재까지
  알려진 evidence judgment와 review status를 저장한다.
- 실제 실행 결과는 이 디렉터리에 섞지 않는다. `TrialRunResult`와 비교 보고서는
  versioned run 디렉터리에 별도로 기록한다.
- manifest가 가리키는 source fingerprint와 spec fingerprint가 달라진 경우 같은
  benchmark/run으로 덮어쓰지 않고 새 version을 만든다.

## 3. Historical snapshot

[`pre-redesign-historical-v1.json`](historical/pre-redesign-historical-v1.json)은 Golden
V1/V2/V3 dataset 42개 파일과 과거 result 8개 파일, 총 50개 파일 약 24.9 MB를
checksum manifest로 동결한다. 파일 복사본이 아니라 명시적 scope, 상대 경로,
category, byte size, SHA-256을 저장한다.

`launchpilot.evaluation.portfolio.snapshot.verify_manifest`는 다음 drift를 모두
오류로 보고한다.

- manifest에 있던 파일의 누락 또는 내용 변경
- 동결 scope 아래 새 파일 추가
- scope의 file/directory 형태 변경
- scope 누락이나 category 충돌

동결은 과거 결과의 정당성을 새로 보증하는 절차가 아니다. 과거 결과를 당시
artifact와 함께 해석할 수 있도록 lineage를 고정하는 절차다. 수정이 필요하면 기존
scope를 고치지 말고 새 dataset/result version을 만든다.

## 4. Golden V2 후보 포트폴리오

선별기는 Golden V2의 680개 synthetic case를 대상으로 tool/route hint나 기존 system
score를 사용하지 않는다. declared leakage group, entity, evidence source,
template-style key의 연결 성분을 만든 뒤 서로 다른 portfolio 사이에 성분이 겹치지
않도록 배치한다.

### 4.1 Frozen candidate

현재 후보는 64건이다.

- 48건: deterministic fact로 대조 가능한 `auto_validated`, `ready`
- 16건: 고가치 safety case, `needs_review`, `pending_human_review`

16건은 Frozen에 포함할 가치가 있어 선별했을 뿐 review gate를 통과한 것이 아니다.
따라서 검수 전에는 48건짜리 제한된 deterministic slice와 64건짜리 완성 Frozen을
구분해서 보고한다. 48건 결과도 synthetic fixture에서의 상대 비교이며 production
대표성 주장은 할 수 없다.

### 4.2 Holdout candidate

보수적인 leakage 연결 결과는 크기 630과 50인 두 성분뿐이다. 50건 성분을 분리하면
leakage-disjoint 조건은 만족하지만, 그 50건은 모두 no-answer 계열이며 모두 human
review 대기다. 그러므로 이 artifact는 다음 두 문제를 숨기지 않고 노출한다.

- 기존 V2 생성 구조가 entity/source/template 차원에서 대부분 하나의 거대 성분으로
  연결되어 있다.
- 분리 가능한 50건은 task/answerability 분포를 대표하지 않는다.

이 50건을 검수해도 대표 Holdout이 되는 것은 아니다. 실제 blind Holdout은 기존
template·entity·source와 분리된 새 문제를 수집하고, answerable/ambiguous/insufficient,
structured/unstructured/mixed 및 주요 task slice를 의도한 운영 분포에 맞게 포함해야
한다. Holdout 내용이나 결과를 보고 architecture를 수정했다면 다음 Holdout version이
필요하다.

### 4.3 Query와 Eval Specification 분리

V2 adapter는 선별 case를 두 계약으로 분리한다.

- Query에는 text, source, portfolio, explanatory characteristics,
  leakage group만 둔다. Dense/BM25/Graph 같은 expected tool은 넣지 않는다. V2
  변환물은 selector가 계산한 leakage component도 보존하므로 통계 코드가 synthetic
  near-duplicate를 독립 query로 세지 않는다.
- Eval Specification에는 answerability, expected behavior, required atomic facts,
  현재 known-relevant evidence와 review status를 둔다.

`semantic`, `entity_centric`, `multi-hop` 같은 값은 slice 분석용 explanatory variable이다.
올바른 route나 tool을 지정하는 정답 label로 사용하지 않는다.

## 5. Golden V3 priority review queue

V3 우선 검수 queue는 39건을 선택한다.

- negative case 29건: answerability와 abstention/clarification 경계를 확인한다.
- cross-campaign comparison 10건: campaign scope, required facts, 다중 source evidence를
  확인하고 불완전한 qrels를 확장한다.

각 row는 현재 query, qrels, expected document/number, causal triad, evidence preview,
review reason을 보여준다. `current_*` 필드는 검수 입력이지 확정 gold가 아니다. queue
파일에는 reviewer decision을 미리 채우지 않으며 manifest는 source와 queue fingerprint,
`awaiting_human_review` 상태를 기록한다.

실제 adjudication에는 최소한 reviewer ID, 판정 시각, rationale, answerability,
required fact 수정, evidence의 known-relevant/known-irrelevant 판정과 relevance grade를
별도 version으로 기록한다. disagreement는 합의 없이 평균하거나 자동 병합하지 않는다.

## 6. Judgment pooling과 `unjudged` 원칙

새 retriever가 기존 qrels에 없던 더 좋은 evidence를 찾을 수 있으므로 qrels 부재는
failure가 아니다. pooling workflow는 다음과 같다.

1. 같은 corpus version에서 비교할 각 system/index run의 top-k hit를 수집한다.
2. `(query_id, corpus_ref)`로 합치되 run, system, index, rank, score, top-k provenance를
   보존한다.
3. 기존 qrel이 있으면 `known_relevant` 또는 `known_irrelevant`를 이어받고, 없으면
   반드시 `unjudged`로 둔다.
4. human adjudication을 병합해 새 pool version을 만들고 parent fingerprint를 남긴다.

`launchpilot.evaluation.portfolio.pooling`은 한 run 안의 rank/ref 중복, corpus version
혼합, 기존 qrel 중복, reviewer 간 judgment/grade 충돌, pool 밖 adjudication을 거부한다.
충돌 없는 batch만 새 immutable snapshot으로 병합한다.

판정이 끝나기 전에는 다음처럼 보고한다.

- known-relevant recall과 judged precision은 판정된 subset에 한정한다.
- `unjudged@k` 또는 judgment coverage를 함께 공개한다.
- unjudged를 0점 relevance로 강제하는 aggregate precision/nDCG로 새 architecture를
  탈락시키지 않는다.
- pool과 qrels가 바뀌면 version을 올리고 과거 score는 당시 version과 함께 보존한다.

## 7. Controlled V0/V1/V2 experiment

`launchpilot.evaluation.controlled_runner`는 시스템을 실제로 구현하는 adapter가 아니라,
동일 조건 비교를 강제하고 결과를 기록하는 harness다. 실행 전 다음 입력이 필요하다.

- review status가 `auto_validated` 또는 `human_reviewed`인 Query/Eval Specification
- V0/V1/V2 각각의 실제 executor adapter와 명시적인 system/index/toolset/code version
- 모든 system에 동일한 corpus, model, prompt
- 사전 선언한 contrast, hypothesis, 변경 필드, pass-rate threshold, trial 수
- 항상 grader ID/code/rubric version을 기록하고, spec rubric compatibility를 명시한
  grader provenance. LLM judge에는 model/prompt version도 필수이며 calibration version은
  실제 human calibration이 있을 때만 기록한다.
- 실제 E2E latency, token, context, tool call, cost를 기록하는 telemetry
- live model/tool 호출 비용과 데이터 접근에 대한 실행 승인

### 7.1 통제와 stochasticity

- query × trial block 순서를 seed로 무작위화하고, 한 block의 모든 system에 같은
  requested seed를 전달한다.
- block 안 system 순서도 무작위화해 cache/order 효과를 완화한다.
- system과 grader 각각의 requested/effective seed, provider/judge request ID,
  시작/종료 시각을 trial마다 저장한다.
- 기본 비교는 query당 3 trials이며 success rate, all-trials-pass, latency/cost 분산을
  평균과 분리해 본다.
- 기본 cache policy는 system별 격리이며 모든 system에 동일 warmup policy를 전달한다.
  외부 adapter가 이를 실제로 적용해야 하고, shared cache는 별도 experimental
  condition으로만 사용한다. provider가 seed를 보장하지 않으면 effective seed와 반복
  분산을 통해 그 한계를 드러낸다.

### 7.2 Gold leakage와 failure semantics

일반 system executor에는 text와 language만 보인다. legacy query ID도
`det_sem_*`, `structured.*`처럼 task/route hint를 담을 수 있어 harness envelope에만
남긴다. taxonomy, required facts, known evidence도 grader 쪽에만 둔다. 기존 qrels의
known-relevant evidence를 주입하는 실험은 별도 `known_gold_evidence_injected`
condition으로만 실행하고 production score와 섞지 않는다. qrels 자체가 불완전하므로
이 결과를 완전한 oracle/capability ceiling으로 부르지 않는다.

- system error/timeout은 production reliability failure이므로 task failure로 집계한다.
- harness 또는 grader failure는 system quality가 아니므로 비교를 중단한다.
- grader failure 전까지 얻은 answer/evidence/telemetry는 보존해 재채점과 원인 분석에
  사용한다. execution, grading, harness failure stage는 별도로 기록한다.
- 수집되지 않은 token/cost 값은 0으로 채우지 않고 missing으로 남기며 telemetry
  completeness를 함께 보고한다.
- tool trace는 routing truth가 아니라 diagnosis 자료다. 첫 tool 선택만으로 outcome을
  fail 처리하지 않는다.

### 7.3 비교와 산출물

V0→V1, V1→V2처럼 marginal contrast를 각각 사전 선언한다. 비교기는 같은 query,
spec version, corpus/model/prompt, trial ID/requested seed를 확인한 뒤 다음을 분리한다.

- Newly Solved, Regression, Pass→Pass, Fail→Fail, Net Gain
- task success rate와 required-fact coverage의 leakage-cluster → matched-trial-pair
  hierarchical bootstrap interval 및 `independent_cluster_count`
- groundedness/relevance의 scored denominator, win/loss/tie/unscored 및 delta
- answer-bearing evidence 확보율과 동일 cutoff에서의 known-relevant recall@k
- completed/failure/timeout rate와 all-trials-pass reliability
- latency p95/standard deviation, cost/tool-call delta, success당 cost/latency
- tool trace와 efficiency telemetry completeness

run writer는 eval dataset lineage, 실제 Query/Eval Specification snapshot, grader와
comparison 설정, randomized schedule, spec fingerprint, system별 trial JSONL,
contrast별 report를 고유 임시 디렉터리에 쓴 뒤 한 번에 publish하며 기존 run을
덮어쓰지 않는다. 중간 write가 실패하면 완성 run은 노출하지 않고 `.failed-*` staging을
남겨 감사와 안전한 재시도가 가능하다. grader/harness failure가 있으면 raw trial은
publish하되 comparison status를 `blocked`로 기록한다.

현재 V2 Frozen 후보 64건은 모두 하나의 leakage connected component에 속한다. 따라서
query 수가 64라고 해서 독립적인 일반화 표본이 64개인 것은 아니다. controlled report의
`independent_cluster_count`가 1이면 interval은 trial stochasticity만 일부 반영할 뿐,
새 campaign/template 분포로의 일반화 불확실성을 추정하지 못한다.

Newly Solved/Regression은 사전 선언 threshold에 따른 point-estimate 기반 설명적 label이다.
bootstrap interval이 이 label을 자동으로 통계적 유의 판정으로 바꾸지는 않는다.

## 8. 아직 완료되지 않은 증거와 다음 순서

현재 repository에는 실제 production query sample, 완료된 human calibration set,
human-reviewed representative Holdout, 새 pooled judgments, 실제 controlled V0/V1/V2
run report가 없다. test executor/grader로 harness를 검증한 결과는 plumbing test이며
architecture 성능 증거가 아니다. 검수되지 않은 LLM judge나 과거 keyword proxy를
primary grader로 연결해 live run을 먼저 실행하면 비용은 들지만 신뢰할 수 있는 결론은
얻지 못한다.

최소 실행 순서는 다음과 같다.

1. Frozen candidate의 safety 16건과 V3 priority 39건을 독립 human review한다.
2. 기존 V2와 독립적인 source/entity/template로 대표 Holdout을 새로 만든다.
3. 비식별화한 production query sample과 human task-success sample을 구축한다.
4. metric별 automated grader를 human judgment에 calibration하고 version을 고정한다.
5. V0/V1/V2 top-k를 pooling해 unjudged evidence를 판정하고 qrels version을 올린다.
6. 동일 corpus/model/prompt에서 query당 최소 3 trials의 controlled run을 실행한다.
7. paired transition, slice delta, reliability, marginal cost/latency로 architecture
   decision record를 작성한다.

48개 ready case만으로 제한된 dry run을 먼저 수행할 수는 있다. 이 경우 결과 이름과
보고서에 `synthetic-auto-validated-slice`를 명시하고, broad capability/release 결론에는
사용하지 않는다. Human calibration과 production sample이 준비되기 전까지 automated
score와 실제 사용자 task success의 상관은 검증되지 않은 상태다.

## 9. 구현 위치

| 역할 | 코드 |
| --- | --- |
| Historical snapshot/verification | `launchpilot.evaluation.portfolio.snapshot` |
| V2 candidate selection/leakage audit | `launchpilot.evaluation.portfolio.benchmark_builder` |
| V2 Query/Eval Specification adapter | `launchpilot.evaluation.portfolio.v2_adapter` |
| V3 priority review queue | `launchpilot.evaluation.portfolio.review_queue` |
| Pooled judgments | `launchpilot.evaluation.portfolio.pooling` |
| Query/Spec/Trial contracts | `launchpilot.evaluation.contracts.architecture_eval` |
| Controlled experiment | `launchpilot.evaluation.controlled_runner` |
| Paired comparison | `launchpilot.evaluation.paired_comparison` |

각 구현의 unit test는 schema, deterministic fingerprint, leakage separation,
no-overwrite, gold redaction, paired seed, failure 처리의 불변식을 검증한다. 이 테스트는
data quality의 사람 판정이나 production validity를 대신하지 않는다.
