# 🚀 Pull Request: V3 골든 데이터셋 구축 및 LangGraph 인-루프 Agentic RAG 파이프라인 구현

## 📌 PR 한 줄 요약 (BLUF)
구글 종속적 SDK 및 레거시 휴리스틱 파이프라인을 걷어내고, **업계 표준 LangGraph StateGraph + 인-루프 Evidence Organizer(Reranker) + Gemini 3.7 Flash(Vertex AI ADC) + Arize Phoenix OTel 관측 환경**을 구축하여, **150건의 V3 골든 데이터셋 감사 통과 및 3단계 어블레이션 실측 검증**을 완료했습니다.

---

## 🏛️ 1. 핵심 아키텍처 변경 사항

### ① 완전한 LangGraph 순환형 인지 루프 (In-Loop Evidence Organizer)
* **토폴로지**: `START` -> `RouterNode(Scope 앵커링)` -> `AgentNode` <-> `ToolNode(도구 인출)` -> `EvidenceOrganizerNode(자료 정렬)` -> `AgentNode(최종 합성)` -> `END`.
* **실측 효과**: 다중 턴에서 인출된 원시 자료들을 시계열 및 도메인 우선순위로 정렬하여 에이전트의 워킹 메모리에 제공함으로써, **방해물 충돌 상황에서 도구 호출 50% 절감 (10회 -> 5회)** 확인.

### ② 전처리 계층의 비파괴적 스코프 앵커링 확립 (ADR 0007)
* **의도 해체기(IntentParser) 제거**: 전처리기에서 질문을 임의로 재작성할 경우 발생하는 인과 맥락 평탄화 및 단어 고착 결함을 실측 규명하고 제거.
* **ScopeRouter 단독 채택**: 원문 질문을 그대로 전달하고 세션 스코프만 0초 만에 앵커링하여 최단 지연시간(8.08s) 달성.

### ③ Causal Knowledge Graph의 1-Hop 원자적 인과 인출
* 플랫 검색기의 검색 뺑뺑이(Search Thrashing) 현상을 Causal Graph(`traverse_campaign_graph`)로 완화하여 **1회 호출로 [기획 지침 -> 이상치 -> 조치 -> 회고] 3-Hop 인과 체인 완결**.

---

## 📊 2. 3대 점진적 어블레이션 및 스트레스 테스트 실측 성적

### [A] 3대 점진적 어블레이션 (Phase 1 ~ Phase 3)
| 실험 단계 | 파이프라인 구성 | 팩트 정확도 (Faithfulness) | 평균 지연시간 (Latency) | 도구 호출 수 (Invocations) |
| :--- | :--- | :---: | :---: | :---: |
| **Phase 1-A** | Classic (SQL + BM25) | 100.0% (4/4) | 17.91 초 | 41 회 (BM25 29회 호출) |
| **Phase 1-C** | + Causal Knowledge Graph | 100.0% (4/4) | 15.06 초 | 33 회 (BM25 68.9% 절감) |
| **Phase 2** | + ScopeRouter 단독 앵커링 (ADR 0007) | 100.0% (4/4) | **8.08 초** | **9 회 (최단 지연시간)** |
| **Phase 3** | + In-Loop Evidence Organizer (Reranker) | 100.0% (4/4) | 24.31 초 | 9 회 (자료 정렬 및 전수 인용) |

### [B] 현실적 적대적 스트레스 테스트 (Adversarial Stress Test)
| 고난도 챌린지 케이스 | Phase 2 (Reranker 없음) | **Phase 3 (In-Loop Reranker)** | 실측 비교 |
| :--- | :---: | :---: | :--- |
| **1. 시계열 방해물 충돌 (3월 초순 입찰가 조정)** | 도구 6회 호출 (`45.46s`) | **도구 3회 호출 (`57.37s`)** | **도구 낭비 50% 절감** |
| **2. 동일 광고주 내 캠페인 크로스 판별** | 도구 1회 호출 (`5.38s`) | 도구 1회 호출 (`17.57s`) | 두 파이프라인 모두 단독 식별 |
| **3. 지표-조치-회고 3-Hop 결합 추론** | 도구 3회 호출 / 45.27 초 | **도구 1회 호출 / 9.03 초** | **지연 시간 -80% 단축** |
| **총 도구 호출 수 합계** | **10 회** | **5 회** | **고난도 환경 도구 50% 절감** |

---

## 📁 3. 주요 변경 파일 및 추가 문서

1. **아키텍처 및 파이프라인 코어**:
   * `services/launchpilot-api/src/launchpilot/analysis/graph.py`: LangGraph `StateGraph(MessagesState)` 인-루프 토폴로지.
   * `services/launchpilot-api/src/launchpilot/analysis/router.py`: 비파괴적 `ScopeRouter` 단독 전처리 노드.
   * `services/launchpilot-api/src/launchpilot/analysis/reranker.py`: LLM 기반 Listwise Domain Reranker.
   * `services/launchpilot-api/src/launchpilot/analysis/prompts.py`: 동적 컨텍스트 주입 및 자율 도구 가이드라인.
2. **벤치마크 및 평가 엔진**:
   * `services/launchpilot-api/evals/agentic_progressive_ablation.py`: 실시간 OTel 계측 및 3단계 어블레이션 러너.
   * `services/launchpilot-api/evals/stress_test_phase2_vs_phase3.py`: 3대 현실적 고난도 맞대결 러너.
   * `services/launchpilot-api/tests/test_marketing_golden_v3_audit.py`: 2세대 동적 적대적 검증 테스트 (10/10 PASS).
3. **공식 문서 및 보고서**:
   * `docs/rebuild/comprehensive-agentic-rag-ablation-report.md`: 3단계 종합 결산 보고서.
   * `docs/rebuild/adr/0007-elimination-of-intent-parser-in-preprocessing.md`: ADR 0007 아키텍처 결정서.
   * `docs/rebuild/dataset-evolution-v1-to-v3.md`: V1 -> V2 -> V3 데이터셋 진화 보고서.

---

## 🔮 4. V3 그 이상의 발전 로드맵 (Future Roadmap)

1. **Self-Correction & Reflexion 자가 교정 노드**: 에이전트가 인출된 근거에 불확실성이 있을 때 능동적으로 반례를 재탐색하는 자기 성찰 루프 고도화.
2. **Multi-Campaign Scatter-Gather Matrix**: 크로스 캠페인 비교 시 다중 서브그래프를 병렬로 동시 순회하는 분산 탐색 파이프라인.
3. **E2E 프로덕션 스트리밍 서빙**: FastAPI 엔드포인트와 Phoenix OTel 대시보드의 실시간 프로덕션 모니터링 연동.
