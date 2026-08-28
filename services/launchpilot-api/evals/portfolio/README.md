# Eval Portfolio 운영 가이드

> 상태: 평가 재설계의 데이터·실행 기반은 구현되었지만 release benchmark는 아직
> 준비 중이다. 이 문서는 무엇이 실제로 생성되었고 무엇이 아직 증명되지 않았는지를
> 구분한다.

이 포트폴리오의 목적은 같은 문제 공간에서 retrieval/agent architecture를 바꿀 때
capability gain, regression, reliability, cost를 paired experiment로 판단하는 것이다.
Golden V1/V2와 그 결과는 historical archive로만 보존한다. 신규 benchmark의 query,
gold, slice, regression seed, holdout을 선정하거나 architecture 성능을 판단할 때
V1/V2를 입력으로 사용하지 않는다. 현재 문제 공간은 V3와 이후의 production sample을
감사해 새 Problem/Eval Specification/Trial Result 계약으로 다시 구성한다. V3
provenance의 첫 이관본은
[`../datasets/marketing-ops-task-v1`](../datasets/marketing-ops-task-v1/)이며 frontier
draft라서 release 판단에는 사용할 수 없다.
Dataset lifecycle의 machine-readable 기준은
[`golden/dataset-registry.json`](../golden/dataset-registry.json)에 있다.

상세한 감사 근거와 평가 철학은
[Evaluation System Audit](../../../../docs/reports/evaluation-system-audit.md), target
architecture는
[Evaluation Architecture](../../../../docs/architecture/evaluation-framework.md)를
참조한다.

## 1. 현재 상태와 사용 가능 범위

| 자산 | 현재 상태 | 지금 가능한 사용 | 아직 하면 안 되는 주장 |
| --- | --- | --- | --- |
| Historical snapshot | 50개 파일의 경로·크기·SHA-256 동결 완료 | 과거 dataset/result drift 탐지, 재현성 기준점 | 과거 proxy score가 production quality를 입증한다는 주장 |
| Golden V1/V2 archive | checksum snapshot으로 보존 | 과거 구현·결과의 계보 확인 | 신규 benchmark나 regression source로 재사용 |
| Active Frozen/Holdout | 아직 없음 | V3/current corpus와 production sample의 admission 기준 설계 | archive dataset을 변환해 현재 benchmark라고 주장 |
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
└─ review/
   ├─ v3-priority-review.jsonl
   └─ v3-priority-review.manifest.json
```

- `datasets/*/problems/problems.jsonl`: 사용자가 해결하려는 problem, supplied context와
  분석용 characteristics만 저장한다.
- `datasets/*/specifications/eval-specifications.jsonl`: answerability, required facts,
  expected behavior와 review status를 저장한다.
- `datasets/*/judgments/evidence-assessments.jsonl`: 현재까지 판정된 evidence를
  known relevant/irrelevant로 저장하며 목록 밖 evidence는 unjudged다.
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

## 4. Active benchmark admission

Golden V1/V2는 새 schema로 변환하거나 일부 case를 선별해 Frozen/Regression으로
이관하지 않는다. archive의 구조적 완성도는 현재 information need 대표성의 근거가
아니기 때문이다.

새 active portfolio는 다음 순서로만 만든다.

1. V3와 현재 corpus·실행 경로를 감사해 실제 지원하려는 problem space를 정의한다.
2. 비식별 production sample로 query/task/answerability 분포를 추정한다.
3. Query와 Eval Specification을 처음부터 분리해 작성한다.
4. evidence는 pooling 후 `known_relevant`, `known_irrelevant`, `unjudged`로 판정한다.
5. entity/source/template leakage group 단위로 Frozen과 blind Holdout을 분리한다.
6. human review와 grader calibration을 통과한 version만 release comparison에 사용한다.

`semantic`, `entity_centric`, `multi-hop` 같은 값은 slice 분석용 explanatory variable일
뿐 올바른 route나 tool을 지정하는 정답 label이 아니다. Active Frozen이 승인되기
전까지 controlled runner 결과는 harness validation이지 architecture capability
증거가 아니다.

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

일반 system executor에는 user utterance, language, world ID와 supplied context만 보인다. legacy query ID도
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

Optional groundedness/relevance/retrieval delta는 양쪽 모든 paired trial의 scored coverage가
완전하고 retrieval cutoff가 같을 때만 계산한다. coverage가 다르면 각 system의 조건부
평균과 scored rate는 진단용으로 남기되 delta는 `null`로 둔다.

run writer는 eval dataset lineage, 실제 Query/Eval Specification snapshot, grader와
comparison 설정, randomized schedule, spec fingerprint, system별 trial JSONL,
contrast별 report를 고유 임시 디렉터리에 쓴 뒤 한 번에 publish하며 기존 run을
덮어쓰지 않는다. 중간 write가 실패하면 완성 run은 노출하지 않고 `.failed-*` staging을
남겨 감사와 안전한 재시도가 가능하다. grader/harness failure가 있으면 raw trial은
publish하되 comparison status를 `blocked`로 기록한다.

Active benchmark는 leakage connected component를 독립 표본 단위로 기록해야 한다.
query 수가 많아도 component 수가 작으면 새 entity/template 분포로의 일반화
불확실성을 추정할 수 없다.

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

1. V3 priority 39건을 독립 human review한다.
2. 현재 corpus와 production problem space에서 source/entity/template가 분리된 대표
   Frozen과 Holdout을 새로 만든다.
3. 비식별화한 production query sample과 human task-success sample을 구축한다.
4. metric별 automated grader를 human judgment에 calibration하고 version을 고정한다.
5. V0/V1/V2 top-k를 pooling해 unjudged evidence를 판정하고 qrels version을 올린다.
6. 동일 corpus/model/prompt에서 query당 최소 3 trials의 controlled run을 실행한다.
7. paired transition, slice delta, reliability, marginal cost/latency로 architecture
   decision record를 작성한다.

Human calibration과 production sample이 준비되기 전까지 automated score와 실제
사용자 task success의 상관은 검증되지 않은 상태다. Golden V1/V2를 이용한 dry run도
active architecture evidence로 보고하지 않는다.

## 9. 구현 위치

| 역할 | 코드 |
| --- | --- |
| Historical snapshot/verification | `launchpilot.evaluation.portfolio.snapshot` |
| V3 priority review queue | `launchpilot.evaluation.portfolio.review_queue` |
| Pooled judgments | `launchpilot.evaluation.portfolio.pooling` |
| Query/Spec/Trial contracts | `launchpilot.evaluation.contracts.architecture_eval` |
| Controlled experiment | `launchpilot.evaluation.controlled_runner` |
| Paired comparison | `launchpilot.evaluation.paired_comparison` |

각 구현의 unit test는 schema, deterministic fingerprint, leakage separation,
no-overwrite, gold redaction, paired seed, failure 처리의 불변식을 검증한다. 이 테스트는
data quality의 사람 판정이나 production validity를 대신하지 않는다.
