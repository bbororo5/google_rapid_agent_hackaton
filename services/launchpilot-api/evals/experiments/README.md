# Retrieval Experiment Matrix

이 디렉터리는 Golden Dataset은 고정한 채 `Chunker × Retriever × 설정값`만
바꾸는 반복 실험을 정의한다. 특정 방식이 정답이라는 라벨은 Golden에 넣지 않고,
모든 조합이 동일한 corpus, qrels, split, metric 구현을 공유한다.

## v1 실험 범위

- Chunker 7개: whole document, fixed token 256/400/512, sentence, recursive,
  semantic
- Retriever 10개: BM25 Top-K 2개, Dense, Korean TF-IDF Sparse, Hybrid alpha
  0.25/0.50/0.75, Dense/Sparse RRF, Reranker 조합
- 총 조합: tune split 기준 70개

v1은 외부 API나 모델 다운로드 없이 재현되는 한국어 마케팅 기준선을 제공한다.

- Dense: 마케팅 지표·추세·진단 동의어를 정규화한 512차원 feature hashing
- Sparse: 한국어 단어·2/3-gram TF-IDF
- Hybrid: BM25와 Dense/Sparse의 weighted score 또는 RRF
- Reranker: query-passage term/concept/number 교차 feature 점수
- Semantic chunker: 인접 문장의 dense cosine breakpoint

미지원 adapter, 빈 corpus, 빈 평가 slice는 0점 대신 `blocked`로 기록한다. 0점과
실행 불가는 분석상 전혀 다른 상태이기 때문이다.

## 평가 지표

- `Recall@K`: 정답 passage 중 검색된 비율
- `MRR@K`: 첫 정답 청크 순위의 역수
- `nDCG@K`: graded qrels와 순위를 함께 반영
- `Context Precision@K`: 검색 문맥 중 중복을 제외한 정답 청크 비율
- `latency_p50_ms`, `latency_p95_ms`: 검색 호출 지연시간

전체 평균과 함께 query profile 및 taxonomy 12개 축별 slice 결과를 저장한다.
동일 passage를 겹치는 여러 청크가 검색해도 정답 이득은 한 번만 계산한다.

## 실행

```powershell
launchpilot-run-retrieval-evals `
  --matrix evals/experiments/retrieval-matrix-v1.yaml `
  --golden-root evals/golden/golden-v1 `
  --output evals/runs/retrieval-matrix-v1 `
  --database-url postgresql://launchpilot:launchpilot-local@127.0.0.1:55432/launchpilot
```

`--require-completed`를 추가하면 완료 조합이 하나도 없을 때 CI가 실패한다.

## 결과 저장

- `retrieval_experiment_runs`: 조합 manifest, 상태, 전체 지표
- `retrieval_experiment_case_results`: 질문별 순위·점수·지연시간·지표
- `retrieval_experiment_slice_metrics`: taxonomy slice별 집계값
- `evals/runs/...`: 사람이 읽는 실행 보고서와 gzip JSONL bundle

matrix를 한 번 실행할 때 생성되는 모든 조합은 동일한 `execution_id`를 가진다.
따라서 같은 `matrix_version`을 반복 실행해도 실행 회차별 비교와 재현이 가능하다.

선택 순서는 tune 후보 축소 → validation 선택 → blind holdout 1회 검증이다.
Accuracy 하나로 선택하지 않고 nDCG/Recall, 최저 slice, 지연시간과 비용을 함께 본다.

## 현재 상태

2026-08-16 실행에서는 캠페인 문서 900개와 문서형 Golden 130개를 사용했다.

- tune: 70/70 완료, blocked 0
- validation shortlist: 12/12 완료, blocked 0
- blind holdout: 선택된 1개 조합을 1회 실행, blocked 0
- 최종 선택: whole document + marketing concept-hash Dense Top-10
  - validation: Recall 1.0000, nDCG 0.9666, query-profile floor 0.9131
  - holdout: Recall 1.0000, nDCG 0.9382, query-profile floor 0.8393

선택 결과는 `selected-retrieval-v1.yaml`에 실행 ID와 함께 고정했다. 이는 합성
corpus용 재현 가능한 기준선이며, 향후 실제 문서와 pretrained embedding을 연결할
때 동일 Golden/metric 계약으로 다시 비교해야 한다.
