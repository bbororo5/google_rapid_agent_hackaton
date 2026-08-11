# Golden Dataset v1

`golden_dataset_v1.jsonl`은 협업자가 함께 검수한 질문만 담는다. UUID처럼 실행마다 달라지는 값 대신 `scenario_id`와 `campaign_ref`로 범위를 식별하고, Eval runner가 실행 환경의 실제 ID로 변환한다.

작성 원칙은 세 가지다.

- `structured` 질문은 정확한 `expected_facts`와 원본 `provenance_prefixes`를 기록한다. Fetch 실행 ID는 매번 달라질 수 있으므로 `meta-ads:`처럼 안정적인 출처 prefix를 사용한다.
- `textual` 질문은 정답 문서뿐 아니라 정답 근거 문장인 `passage`를 기록한다.
- 질문 문구를 바꾸더라도 Ground Truth는 사람이 원본 데이터를 확인한 뒤 확정한다.

현재 `golden_dataset_v1.example.jsonl`은 스키마 검증용 예시다. 협업 검수 후 실제 Dataset으로 승격하며, Phase 3B의 모든 Retrieval 방식은 같은 Dataset을 사용한다.
