# ADR-0004 — 마케팅 도메인 청킹 전략 (Whole Document & Fixed 400)

> 상태: **채택** · 결정일: 2026-08-19

## Context

마케팅 RAG 시스템의 문서(기획서, 운영 메모, 성과 분석 리포트)는 일반 웹 텍스트와 달리 200~600토큰 내외의 독립적인 비즈니스 완결 단락으로 구성됩니다.  
문서를 무분별하게 문장 단위나 소형 청크(100토큰)로 쪼갤 경우 원인-조치 간의 인과 문맥이 파편화되어 검색 및 인용 품질이 급락하는 딜레마가 존재했습니다.

## Options

| 청킹 후보 | 장점 | 한계 | Golden v2 정량 지표 |
| :--- | :--- | :--- | :---: |
| **Whole Document (전체 문서)** | 200~600토큰 문서 인과관계 완결성 100% 보존 | 문서 길이가 1,000토큰을 초과할 경우 임베딩 희석 | **Recall 0.5952 / MRR 0.5599 (1위)** |
| **Fixed 400 Token** | 고정 길이 분할로 검색기 호환성 및 안정성 우수 | 청크 경계에서 간헐적 문맥 절단 발생 | Recall 0.5238 / MRR 0.4290 |
| **Sentence Split (문장 분할)** | 매우 세밀한 단위 인출 가능 | 문맥 파편화로 단독 단락의 의미 전달력 상실 | Recall 0.5357 / MRR 0.4315 |

## Decision

- **Primary 청킹**: 200~600토큰 길이의 마케팅 문서는 **Whole Document 청킹(900개 청크)**을 기본 전략으로 채택한다.
- **Secondary 청킹**: 600토큰 초과 대형 문서는 **Fixed 400 Token 청킹(1,800개 청크, overlap 50)**을 병행 지원한다.
- **메타데이터 바인딩**: 모든 청크에는 인덱싱 시점에 `BRIEF / MEMO / ANALYSIS` 문서 타입 메타데이터를 강제 부착하여 검색 전 사전 필터링을 지원한다.

## References

- [Retrieval Benchmark Evolution](../retrieval-benchmark-evolution.md)
- `services/launchpilot-api/src/launchpilot/analysis/chunker.py`
