# Architecture Decision Records

각 ADR은 하나의 결정을 고정 형식(상태 · 맥락 · 결정 · 결과 · 대안)으로 기록한다. 결정을 강제한 사실과 포기한 것을 함께 적는다. 카테고리별 문서와 상태 반응형 워크플로우 ADR로 나누어 담았다.

| ADR | 결정 | 문서 |
|---|---|---|
| 0001 | Elastic Cloud Serverless를 유일 데이터 저장소로 사용 | [데이터 · 기억](01-data-and-memory.md) |
| 0002 | 에이전트 기억을 네 계층으로 분리 | [데이터 · 기억](01-data-and-memory.md) |
| 0003 | 승인 전 데이터 비저장, 승인 게이트 Java 소유 | [데이터 · 기억](01-data-and-memory.md) |
| 0004 | 단일 LLM 대신 4워커 멀티 에이전트 | [에이전트](02-the-agents.md) |
| 0005 | Google ADK 직접 오케스트레이션 (Agent Builder 미사용) | [에이전트](02-the-agents.md) |
| 0006 | 결정적 검수가 최종 권한, LLM 비평은 보조 | [에이전트](02-the-agents.md) |
| 0007 | 형식 오류는 결정적 정규화, 의미 오류는 워커 백트래킹 | [에이전트](02-the-agents.md) |
| 0008 | 영속 WebSocket 타임라인 + 재접속 리플레이 | [투명성 · 관측성](03-transparency.md) |
| 0009 | Glass-box는 정규화 이벤트만 전송 | [투명성 · 관측성](03-transparency.md) |
| 0010 | Phoenix/Arize L4 자가 성찰 | [투명성 · 관측성](03-transparency.md) |
| 0011 | Contract-first (extra=forbid) | [엔지니어링 규율](04-discipline.md) |
| 0012 | CSV import + 결정적 fallback | [엔지니어링 규율](04-discipline.md) |
| 0013 | [ADR-004] 자유 대화 기반 StateDelta + 결정적 reducer | [상태 반응형 워크플로우](05-state-reactive-workflow.md) |
| 0014 | [ADR-005] 런타임 메모리 적재·조회: Redis 핫 상태 + Elastic 에피소딕 영속 | [메모리 관리](06-memory-management.md) |
| 0015 | Java Backend와 Python Agent Core 통합 4축 관찰성 baseline | [통합 관찰성](07-unified-observability.md) |
| 0016 | GCP 제거 이후 관찰성 3축 기준 | [GCP 이후 관찰성 3축](08-observability-after-gcp.md) |
| 0017 | GCP 이후 로컬/무료 관찰성 스택 후보 선정 | [GCP 이후 관찰성 스택 후보](09-observability-stack-selection.md) |
| 0018 | 복합 실무 에이전트를 위한 Collaborative workflow 선정 | [에이전트 workflow 모델](10-agent-workflow-model.md) |

상위 요약: [아키텍처 개요](../overview.md) · 구조 그림: [C4](../launchpilot-c4.md) · 제품 맥락: [PRD](../../product/LaunchPilot_PRD.md)
