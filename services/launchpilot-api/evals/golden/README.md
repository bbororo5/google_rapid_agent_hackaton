# Golden dataset lifecycle

[`dataset-registry.json`](dataset-registry.json)이 dataset의 사용 가능 범위를 결정한다.

- `golden-v1`, `golden-v2`: historical reproduction 전용 archive다. 신규 benchmark,
  gold migration, regression seed, holdout, architecture release decision에 사용하지 않는다.
- `golden-v3`: 현재 시스템을 감사하기 위한 current fixture다. Human review와 production
  sample 기반의 새 Frozen/Holdout이 승인되기 전에는 release benchmark가 아니다.

버전 숫자가 lifecycle이나 canonical status를 암시한다고 가정하지 않는다. Lifecycle을
바꿀 때는 registry, 근거 문서, review record를 함께 변경한다.
