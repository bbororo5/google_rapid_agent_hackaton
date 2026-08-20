# ADR-0006 — 결정론적 스코프 주입 및 조건부 라우팅 전략 (RouterNode)

> 상태: **채택** · 결정일: 2026-08-19

## Context

초기에는 LLM이 모든 단계에서 자율적으로 라우팅을 수행하도록 설계했으나, 멀티테넌트 환경에서 타 고객사 데이터 접근 위험, 마케터의 상대적 시간 표현("지난주", "어제")에 따른 기준 시점 부재, 비정상 질의에 대한 비결정론적 동작 문제가 발생했습니다.  
따라서 라우터의 책임을 "단순 자율 분기"가 아닌 "보안 스코프 및 메타데이터의 결정론적 주입"으로 정의하는 전환이 필요했습니다.

## Options

| 라우팅 구조 후보 | 장점 | 한계 | 보안/안정성 |
| :--- | :--- | :--- | :---: |
| **결정론적 Scope Router (채택)** | 테넌트 격리 및 시간 앵커 강제 주입, 위험 질의 사전 차단 | 사전 정의된 스코프 규칙 필요 | **100% 격리 (0% 데이터 누출)** |
| **Full LLM Autonomous Router** | 비정형 자연어 분류 유연성 | 환각 및 비결정론적 스코프 누출 위험 | 스코프 이탈 위험 존재 |
| **No Router (단일 패스 에이전트)** | 그래프 구조 단순화 | 기준 시간 부재로 상대 시점 쿼리 100% 왜곡 | 시간 왜곡 100% 발생 |

## Decision

- **1. 스코프 및 메타데이터 결정론적 주입 (`RouterNode`)**:
  - `workspace_id`: 타 테넌트 침범을 원천 차단하는 보안 바인딩.
  - `reference_now = 2026-08-19`: 마케터의 상대적 시점을 고정하는 시스템 시계 주입.
  - **정량 효과**: 동일 캠페인의 이종 문서 노이즈를 100% 차단하여 BM25 MRR을 **0.4962에서 0.6154로 +11.9%p 향상**.
- **2. 조건부 가드레일 분기 (`GuardrailNode` 후속 분리)**:
  - 정상 질의 ➔ `AgentNode`로 진입하여 도구 연쇄 호출.
  - 어트리뷰션 왜곡(Google vs Meta 기준 불일치) 또는 부존재 캠페인(C9999) ➔ `GuardrailNode`로 분기하여 Safe Refusal 즉각 반환.

## References

- [Retrieval Benchmark Evolution](../retrieval-benchmark-evolution.md)
- `services/launchpilot-api/src/launchpilot/analysis/router.py`
- `services/launchpilot-api/src/launchpilot/analysis/graph.py`
