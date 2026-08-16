# Golden Dataset v1

`golden_dataset_v1.jsonl`은 협업자가 함께 검수한 질문만 담는다. UUID처럼 실행마다 달라지는 값 대신 `scenario_id`와 `campaign_ref`로 범위를 식별하고, Eval runner가 실행 환경의 실제 ID로 변환한다.

작성 원칙은 세 가지다.

- `structured` 질문은 정확한 `expected_facts`와 원본 `provenance_prefixes`를 기록한다. Fetch 실행 ID는 매번 달라질 수 있으므로 `meta-ads:`처럼 안정적인 출처 prefix를 사용한다.
- `textual` 질문은 정답 문서뿐 아니라 정답 근거 문장인 `passage`를 기록한다.
- 질문 문구를 바꾸더라도 Ground Truth는 사람이 원본 데이터를 확인한 뒤 확정한다.

현재 `golden_dataset_v1.example.jsonl`은 스키마 검증용 예시다. 협업 검수 후 실제 Dataset으로 승격하며, Phase 3B의 모든 Retrieval 방식은 같은 Dataset을 사용한다.

현재 실행 가능한 Dataset은 [`golden/golden-v1`](golden/golden-v1/)에 있다.
현재 Dataset은 합성 PG 근거와 캠페인별 BRIEF·MEMO·ANALYSIS 900개를 고정해
600개 사례를 제공한다. 단일 조회, 집계, 기간·플랫폼·캠페인 비교, 4주 추세,
추적 누락, 통화·귀속·기간 불일치뿐 아니라 문서 원인 진단, 예산 페이싱,
PG+문서 권고를 포함한다. 문서 사례 130개는 `document_ref + char span`으로
정답 passage를 고정해 청킹 방식을 바꿔도 같은 Ground Truth를 사용한다.

전문 분류 기준은 [`taxonomy.yaml`](taxonomy.yaml), 사람이 읽는 설명은
[`TAXONOMY.ko.md`](TAXONOMY.ko.md)에 있다. 각 Golden 사례에는 12개 분류 축을
기록하고, 분류 무결성과 모델 선택용 커버리지를 별도로 판정한다. 사람 검수에는
`golden/golden-v1/review/case_catalog.csv`를 사용한다.

청킹·검색 방식의 조합 실험은
[`experiments/retrieval-matrix-v1.yaml`](experiments/retrieval-matrix-v1.yaml)에
정의하며, 실행·지표·DB 스키마는 [`experiments/README.md`](experiments/README.md)에
한국어 비교표와 함께 정리했다. Golden에는 Retriever 정답을 넣지 않고 실험
manifest만 분리한다.

```bash
launchpilot-build-golden \
  --database-url postgresql://launchpilot:launchpilot-local@localhost:55432/launchpilot \
  --output evals/golden/golden-v1
```
