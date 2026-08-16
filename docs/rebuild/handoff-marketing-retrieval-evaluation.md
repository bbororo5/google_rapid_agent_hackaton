# Marketing Retrieval Evaluation 인수인계

## 목적

한국어 자연어 캠페인 요청을 PostgreSQL structured retrieval과 문서 검색
(BM25, Dense, Learned Sparse, Hybrid, Reranker)으로 처리하고, 검색·답변 품질을
반복 실험할 수 있는 기반을 마련한다.

이 문서는 합성 PostgreSQL 데이터와 Marketing Golden Dataset 작업을
인수인계하고, 후속 Pull Request 설명의 기준 문안으로 사용한다.

## 현재 완료 상태

- 결정적 seed를 사용하는 합성 마케팅 데이터 생성기를 구현했다.
- 로컬 PostgreSQL에 기본 데이터셋을 실제 적재했다.
  - workspace: 3
  - campaign: 300
  - daily observation: 27,000
  - platform slice: 54,000
  - metric row: 575,226
  - partial observation: 129
- 플랫폼은 `GOOGLE_ADS`, `META_ADS`, `YOUTUBE`를 포함한다.
- 지표는 impressions, clicks, spend, conversions, conversion value, CTR, CVR,
  CPC, CPA, ROAS 및 플랫폼 전용 지표를 포함한다.
- steady, growth, fatigue, launch spike, budget cut, tracking gap, recovery 패턴을
  포함한다.
- 합성 데이터는 전용 사용자와 `synthetic-marketing-v1` provenance로 실제
  데이터와 구분한다.
- `--replace`는 전용 합성 workspace만 교체한다.
- 데이터 감사를 실행하고 검색 방식과 독립적인 `golden-v1`을 생성했다.
  - 전체 사례: 600
  - structured exact: 280
  - lexical identifier: 90
  - no-answer: 30
  - ambiguous: 20
  - adversarial: 50
  - semantic: 50
  - entity semantic: 30
  - mixed structured semantic: 50
  - tune/validation/holdout: 364/117/119
  - 사람 검토 필요: 260
- PG 기반 집계, 기간·플랫폼·캠페인 비교, 4주 추세, 추적 누락 이상 탐지,
  통화·어트리뷰션·기간 불일치 안전성 사례를 각 30개 추가했다.
- 캠페인마다 BRIEF·MEMO·ANALYSIS를 생성해 문서 900개를 고정했다.
- 문서 원인 진단 50개, 예산 페이싱 30개, PG+문서 권고 50개를 추가하고
  130개 정답 passage를 원문 문자 위치로 고정했다.
- W3C SKOS·NIST TREC·공식 광고 지표 정의를 반영한 12축 taxonomy를 적용했다.
  - marketing domain, analysis task, business objective, funnel stage
  - metric family, scope, temporal granularity, difficulty
  - evidence type, answer mode, language style, risk types
- 각 개념에는 표준 코드, 한영 선호명, 동의어, 정의, 포함·제외 규칙과 예시가
  있으며 `taxonomy_version`과 snapshot hash를 manifest에 고정한다.
- 사람 검수용 UTF-8 CSV와 taxonomy coverage report를 생성한다.
- 현재 600개 사례의 분류 무결성은 통과했으며 L1~L5와 모든 analysis task를
  포함한다. 단 no-answer·ambiguity·unsupported-causality가 slice당 50개 미만이라
  production model-selection coverage는 아직 미달이다.
- 7개 Chunker와 10개 Retriever 설정을 조합하는 70개 실험 matrix를 추가했다.
- Recall@K, MRR@K, nDCG@K, Context Precision@K, p50/p95 latency를 동일 구현으로
  계산하며 taxonomy 12개 축별 slice 결과를 PostgreSQL에 저장한다.
- 동일 matrix의 반복 실행이 섞이지 않도록 각 실행 회차에 `execution_id`를
  부여하고, 해당 회차의 모든 조합이 이를 공유한다.
- 외부 모델 다운로드 없이 동작하는 마케팅 concept-hash Dense, 한국어 TF-IDF
  Sparse, Hybrid, 교차 feature Reranker, semantic chunker adapter를 연결했다.
- tune 70/70, validation 12/12, blind holdout 1/1이 완료됐으며 blocked는 0이다.
- 최종 선택은 whole-document + marketing concept-hash Dense Top-10이다.
  validation nDCG 0.9666, holdout nDCG 0.9382, 두 split의 Recall은 1.0이다.

현재 로컬 Docker PostgreSQL은 Windows의 기존 5432 포트와 충돌하여
`localhost:55432`에서 실행 중이다. Docker volume은 로컬 상태이며 PR에
포함되지 않는다.

## 중요한 설계 결정

1. 합성 PostgreSQL 데이터는 개발·반복 실험용 corpus다. 그 자체가 Golden
   Dataset의 qrels 또는 정답 판정은 아니다.
2. Golden Dataset은 특정 retriever를 정답으로 지정하지 않는다. 동일한 질문,
   expected facts, 원문 span을 모든 검색 방식이 공유한다.
3. 정확한 수치와 캠페인 관계는 PostgreSQL을 authoritative source로 사용한다.
4. 의미, 관찰, 진단, 권고는 문서의 원문 근거를 사용한다.
5. 수치와 해석을 함께 묻는 질문은 `pg_and_documents`로 평가한다.
6. 정답 span은 chunk ID가 아닌 `document_ref + char_start + char_end`로 고정한다.
   이 방식이어야 chunker를 바꾸어도 동일한 Golden Dataset으로 비교할 수 있다.
7. 모든 데이터셋 분할은 Golden으로 부른다. 운영 목적에 따라 tune 60%,
   validation 20%, blind holdout 20%로 분리한다.
8. 평균 Accuracy만 최적화하지 않는다. query slice별 Recall@K, MRR, nDCG,
   correctness, groundedness, no-answer F1, latency와 cost를 함께 추적한다.
9. `matrix_version`은 실험 정의의 버전이고 `execution_id`는 실제 실행 회차다.
   조합별 결과는 `experiment_id`로 식별한다.

현재 Golden Dataset은 합성 PG의 선택 근거를 corpus snapshot으로 고정한다.
향후 실제 데이터 연결 시 동일한 Dataset 계약을 유지한 채 source와 정답을
재생성한다.

## 관련 파일

- `services/launchpilot-api/src/launchpilot/devtools/synthetic_marketing.py`
- `services/launchpilot-api/src/launchpilot/evaluation/golden_builder.py`
- `services/launchpilot-api/tests/test_synthetic_marketing.py`
- `services/launchpilot-api/tests/test_marketing_golden_v1.py`
- `services/launchpilot-api/evals/taxonomy.yaml`
- `services/launchpilot-api/evals/TAXONOMY.ko.md`
- `services/launchpilot-api/evals/golden/golden-v1/`
- `services/launchpilot-api/evals/experiments/retrieval-matrix-v1.yaml`
- `services/launchpilot-api/src/launchpilot/evaluation/experiments/`
- `services/launchpilot-api/tests/test_retrieval_experiments.py`
- `services/launchpilot-api/pyproject.toml`
- `services/launchpilot-api/compose.yaml`
- `services/launchpilot-api/README.md`

## 실행 방법

```powershell
cd services/launchpilot-api
$env:POSTGRES_PORT = "55432"
docker compose up -d postgres

uv run launchpilot-seed-synthetic `
  --database-url "postgresql://launchpilot:launchpilot-local@localhost:55432/launchpilot" `
  --workspaces 3 `
  --campaigns-per-workspace 100 `
  --days 90 `
  --seed 20260813 `
  --replace

uv run launchpilot-build-golden `
  --database-url "postgresql://launchpilot:launchpilot-local@localhost:55432/launchpilot" `
  --output "evals/golden/golden-v1"

uv run launchpilot-run-retrieval-evals `
  --matrix "evals/experiments/retrieval-matrix-v1.yaml" `
  --golden-root "evals/golden/golden-v1" `
  --output "evals/runs/retrieval-matrix-v1" `
  --database-url "postgresql://launchpilot:launchpilot-local@localhost:55432/launchpilot"
```

규모를 늘릴 때는 workspace, campaign, days만 변경한다. 같은 seed와 규모를
사용하면 식별자와 수치가 동일하게 재생성된다.

## 검증 상태

다음 검증을 완료했다.

- 전체 테스트 83개 통과
- Ruff 검사 통과
- CTR 계산 불일치 0건
- CVR 계산 불일치 0건
- ROAS 계산 불일치 0건
- 실제 workspace를 보존하면서 synthetic namespace만 교체하는 통합 테스트 통과
- Golden case ID 중복, qrels 참조 누락, 분할 누출, 정규화 질문 중복 0건
- 특정 retriever를 정답으로 지정한 사례 0건
- taxonomy 누락·미등록 코드·cardinality·교차 규칙 위반 0건

검증 명령:

```powershell
$env:TEST_DATABASE_URL = "postgresql://launchpilot:launchpilot-local@127.0.0.1:55432/launchpilot_test"
$env:TEST_ELASTICSEARCH_URL = "http://127.0.0.1:9200"
uv run pytest -q
uv run ruff check src/launchpilot/evaluation src/launchpilot/devtools/synthetic_marketing.py src/launchpilot/persistence/postgres.py tests/test_retrieval_experiments.py tests/test_marketing_golden_v1.py tests/test_synthetic_marketing.py
```

## 후속 작업

1. 합성 문서와 char span 130개를 마케팅 전문가가 검수한다.
2. no-answer·ambiguity·unsupported-causality를 각 50개 이상으로 보강한다.
3. 실제 데이터와 pretrained multilingual embedding을 연결한 뒤 현재 로컬
   concept-hash 기준선과 동일 matrix로 비교한다.
4. 실제 데이터가 준비되면 합성 seed를 제거하지 않고 비활성화한 뒤 source
   adapter만 실제 ingestion으로 교체한다.

## 후속 PR 작성 기준

권장 제목:

```text
feat(evals): add deterministic synthetic marketing data for retrieval experiments
```

권장 요약:

```text
- add a deterministic PostgreSQL seed generator for multi-platform campaign metrics
- isolate replaceable synthetic data with a dedicated user and provenance namespace
- cover realistic performance patterns and partial tracking observations
- build a method-independent 600-case Marketing Golden Dataset from PG and documents
- cover aggregation, comparisons, trends, tracking gaps, and unsafe comparisons
- add a governed 12-axis marketing retrieval taxonomy and coverage gates
- export a human-review CSV with professional category labels
- freeze 900 synthetic campaign documents and 130 document passage spans
- allow PostgreSQL host-port override for local port conflicts
```

권장 테스트 문안:

```text
- 83 tests passed
- Ruff passed
- 300 campaigns / 27,000 observations / 575,226 metric rows loaded
- 600 Golden cases / 3,390 qrels / 3,006 PG records / 900 documents generated
- CTR, CVR, and ROAS consistency violations: 0
- Golden validation checks: all 0
- Taxonomy assignment and cross-rule violations: 0
- Taxonomy coverage readiness: false, with explicit gap report
```

PR을 만들 때는 위 관련 파일과 이 인수인계 문서만 우선 포함한다. 작업 트리의
기존 미추적 디렉터리나 사용자 작업은 별도 확인 없이 함께 stage하지 않는다.
