# ADR-0005 — 초저지연 마케팅 도메인 피처 리랭킹 전략 (MarketingDomainReranker)

> 상태: **채택** · 결정일: 2026-08-19

## Context

1차 Dense 임베딩 검색은 의미적 유사성은 포착하지만, 마케팅 특화 어휘나 질의 의도에 부합하는 문서 타입 적합도를 정밀하게 반영하지 못해 정답 단락이 2~5위로 밀리는 한계가 있었습니다.  
반면 대규모 Cross-Encoder 리랭커 모델은 200ms 이상의 높은 지연 시간과 서빙 비용을 유발하는 트레이드오프가 존재했습니다.

## Options

| 리랭킹 후보 | 장점 | 한계 | 레이턴시 | 정량 기여도 |
| :--- | :--- | :--- | :---: | :---: |
| **MarketingDomainReranker (채택)** | 도메인 피처(타입 가중치 $w_3=0.15$ + 동의어 매칭) 결합 | 복잡한 일반 상식 추론에는 한계 | **1~3ms** | **Dense MRR +28.5%p 견인 (0.2473 ➔ 0.5323)** |
| **Cross-Encoder (bge-reranker-large)** | 문맥 교차 어텐션으로 최고 수준의 랭킹 정밀도 | GPU 리소스 요구 및 높은 레이턴시 | 150~300ms | 고비용 대비 ROI 낮음 |
| **No Reranker (1차 검색 단독)** | 리랭킹 오버헤드 0ms | 1차 검색 순위의 도메인 정합도 왜곡 방치 | 0ms | Dense 단독 시 MRR 0.2473에 머무름 |

## Decision

- **1~3ms 초저지연 `MarketingDomainReranker` 채택**:
  - $S_{\text{final}} = w_1 \cdot S_{\text{bm25}} + w_2 \cdot S_{\text{dense}} + w_3 \cdot S_{\text{domain\_feature}}$
  - $w_3 = 0.15$의 문서 타입 적합도 가중치와 마케팅 실무 동의어 사전을 결합.
- **정량적 근거**:
  - Dense 검색기와 결합 시 MRR을 0.2473에서 0.5323으로 +28.5%p 대폭 향상.
  - Hybrid 검색기와 최종 결합 시 **MRR 0.6173 / nDCG 0.6187**로 전체 12개 파이프라인 조합 중 1위를 달성.

## References

- [Retrieval Benchmark Evolution](../retrieval-benchmark-evolution.md)
- `services/launchpilot-api/src/launchpilot/analysis/reranker.py`
