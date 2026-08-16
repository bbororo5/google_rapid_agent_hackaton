# Golden Dataset v1 설계 문서

이 문서는 `golden-v1`을 **어떤 데이터로, 어떤 질문 카테고리와 정답 구조로
구성했는지** 설명한다. 검색 실험 결과는
[`experiments/README.md`](experiments/README.md)에서 별도로 다룬다.

현재 Golden은 평가 파이프라인과 검색 방식 비교를 위한 합성 기준선이다. 이름이
Golden이라고 해서 모든 사례가 사람 검수를 끝냈다는 뜻은 아니다. 600건 중
340건은 규칙 기반 자동 검증을 통과했고, 판단이 필요한 260건은 전문가 검수
대기 상태다.

## 1. 한눈에 보는 현재 구성

| 항목 | 구성 |
| --- | --- |
| Golden 버전 | `golden-v1` |
| 전체 질문 | 600건, 모두 한국어 |
| 질문 프로필 | 8개 |
| 업무 시나리오 | 15개 |
| 근거 출처 | PostgreSQL 470건 / 문서 80건 / PG+문서 50건 |
| 합성 데이터 | workspace 3개, campaign 300개 |
| 캠페인 문서 | 900개: BRIEF·MEMO·ANALYSIS 각 300개 |
| 분할 | Tune 364 / Validation 117 / Holdout 119 |
| 자동 검증 | 340건 |
| 사람 검수 필요 | 260건 |
| 실제 문서 검색 평가 대상 | 문서 근거가 있는 130건 |

실제 평가 파일은 [`golden/golden-v1`](golden/golden-v1/)에 있다.
`golden_dataset_v1.example.jsonl`은 필드 구조를 보여주는 예시일 뿐 실제 600건
Dataset은 아니다.

## 2. 무엇을 평가하려고 만들었는가

사용자 질문을 단순히 Dense와 Sparse로 나누는 것이 아니라, 먼저 질문이 요구하는
근거와 답변 행위를 고정했다.

- 정확한 캠페인 ID·이름·기간·수치 조회
- 기간·플랫폼·캠페인 간 집계와 비교
- BRIEF·MEMO·ANALYSIS에서 원인과 목표 근거 검색
- PG 수치와 문서 설명을 함께 사용한 권고
- 존재하지 않거나 모호한 캠페인에 대한 답변 거부·재질문
- 통화·기간·어트리뷰션 기준이 다른 비교 요청의 안전한 처리

Golden에는 “BM25가 정답”, “Dense가 정답” 같은 검색 방식 라벨을 넣지 않는다.
동일한 질문·근거·정답을 고정하고, 청킹과 Retriever만 바꾸어 공정하게 비교한다.

## 3. 기반 데이터 환경

모든 데이터는 실제 고객 데이터가 아닌 재현 가능한 합성 데이터다. 생성 결과와
원본 해시는 `manifest.json`에 고정되어 같은 버전을 다시 확인할 수 있다.

| 데이터 | 규모와 특성 |
| --- | --- |
| Workspace | 3개 |
| Campaign | 300개 |
| Campaign observation | 27,000행, `COMPLETE` 26,871 / `PARTIAL` 129 |
| Platform slice | 54,000행 |
| Metric observation | 575,226행 |
| 플랫폼 | Google Ads, Meta Ads, YouTube |
| 통화 | KRW, USD |
| 기간 범위 | 2025-01-01 ~ 2025-09-15 |
| 문서 | 캠페인마다 BRIEF·MEMO·ANALYSIS 1개씩, 총 900개 |

기본 지표는 impressions, clicks, spend, conversions, conversion value이며 파생
지표는 다음 규칙으로 계산했다.

- CTR = clicks / impressions
- CVR = conversions / clicks
- CPC = spend / clicks
- CPA = spend / conversions
- ROAS = conversion value / spend
- 분모가 0이면 파생지표는 0으로 처리한다.

추적 누락 129건과 다중 통화는 오류가 아니라 데이터 품질 및 안전성 질문을
시험하기 위해 의도적으로 포함한 edge case다.

## 4. 600개 질문의 구성

### 4.1 질문 표현과 검색 특성 기준: 8개 프로필

`query_profile`은 사용자의 질문이 어떤 검색 특성을 갖는지 나타낸다.

| 프로필 | 개수 | 근거 | 무엇을 시험하는가 |
| --- | ---: | --- | --- |
| `structured_exact` | 280 | PG | 수치 조회, 집계, 기간·플랫폼·캠페인 비교, 추세 |
| `lexical_identifier` | 90 | PG | 캠페인 코드·UUID·정확한 이름·외부 참조 일치 |
| `semantic` | 50 | 문서 | 자연어로 묻는 성과 원인과 분석 설명 검색 |
| `entity_semantic` | 30 | 문서 | 캠페인 엔터티 식별 후 BRIEF의 목표·페이싱 검색 |
| `mixed_structured_semantic` | 50 | PG+문서 | 정확한 성과 수치와 문서 근거를 결합한 권고 |
| `no_answer` | 30 | PG | 존재하지 않는 캠페인에 답을 만들지 않는지 확인 |
| `ambiguous` | 20 | PG | 중복·불완전 이름에서 임의 선택 대신 재질문하는지 확인 |
| `adversarial` | 50 | PG | 통화·기간·귀속 불일치를 무시하라는 요구에 안전하게 대응 |
| **합계** | **600** |  |  |

이 중 청킹 및 문서 Retriever를 직접 평가하는 사례는 `semantic` 50건,
`entity_semantic` 30건, `mixed_structured_semantic` 50건으로 총 130건이다.
나머지 470건은 정확한 구조화 조회와 라우팅·안전성 평가에 사용한다.

### 4.2 실제 마케팅 업무 기준: 15개 시나리오

프로필이 검색 특성을 설명한다면, 시나리오는 사용자가 실제로 하려는 일을
설명한다.

| 시나리오 | 개수 | 질문의 핵심 |
| --- | ---: | --- |
| 단일 지표 조회 | 100 | 지정한 캠페인·기간·플랫폼의 정확한 수치 |
| 캠페인 식별 | 90 | 코드·이름·UUID로 캠페인과 기간 찾기 |
| No-answer 판정 | 30 | 없는 캠페인이나 근거의 부재 확인 |
| 모호성 확인 | 20 | 후보가 여러 개일 때 clarification 요청 |
| 인과 근거 경계 | 20 | 근거 없이 원인을 단정하지 않기 |
| 집계 | 30 | 여러 행을 합쳐 정확한 총계 계산 |
| 기간 비교 | 30 | 동일 조건의 전주·이전 기간 비교 |
| 플랫폼 비교 | 30 | 플랫폼별 성과 비교 |
| 캠페인 비교 | 30 | 두 캠페인의 동일 지표 비교 |
| 추세 분석 | 30 | 4주 흐름과 방향성 요약 |
| 추적 누락 탐지 | 30 | PARTIAL observation과 전환 누락 경고 |
| 비교 안전성 | 30 | 통화·기간·귀속 조건 불일치 처리 |
| 문서 원인 진단 | 50 | MEMO·ANALYSIS에서 원인 후보 찾기 |
| 문서 목표·페이싱 | 30 | BRIEF에서 목표와 예산 페이싱 근거 찾기 |
| PG+문서 권고 | 50 | 성과 수치와 문서 내용을 결합해 다음 조치 제안 |
| **합계** | **600** |  |

## 5. 정답과 근거를 어떻게 저장했는가

질문 유형이 달라도 모든 사례는 “왜 이것이 정답인지” 추적할 수 있어야 한다.

| 질문 유형 | Ground Truth 구성 |
| --- | --- |
| PG 수치·엔터티 | `expected_facts`에 값·단위·조건을 저장하고 `gold_evidence`로 원본 행을 연결 |
| 문서 검색 | `document_ref`, 정답 문장, `char_start`·`char_end` 범위를 고정 |
| PG+문서 | 정확한 수치 사실과 문서 passage를 모두 정답 근거로 연결 |
| No-answer | `unanswerable=true`, 부재 근거와 abstention 답변을 기록 |
| 모호한 질문 | 충돌 후보와 이유를 기록하고 clarification을 정답 행위로 지정 |
| 안전성 질문 | 통화·기간·귀속 조건과 답변 거부 또는 경고 문구를 기록 |

문서 근거 130건은 청킹 방식을 바꾸더라도 동일한 문자 범위를 정답으로 사용한다.
`qrels.jsonl`에는 질문과 근거의 관련도 등급을 저장하고, `gold_spans.jsonl`에는
사람이 확인할 수 있는 정확한 문장 범위를 저장한다.

## 6. 사례 하나에 들어가는 주요 속성

| 속성 묶음 | 주요 필드 | 역할 |
| --- | --- | --- |
| 식별·버전 | `case_id`, `golden_version`, `taxonomy_version` | 사례와 기준 버전을 고정 |
| 사용자 입력 | `query`, `language`, `language_style` | 실제 평가에 넣을 질문 표현 |
| 검색 라우팅 | `query_profile`, `required_sources` | PG·문서·복합 검색 필요 여부 |
| 범위·조건 | `scope`, `filters` | workspace, campaign, 기간, 플랫폼, 지표 |
| 정답 | `expected_answer`, `acceptable_answers`, `expected_facts` | 값과 허용 가능한 답변 표현 |
| 근거 | `gold_evidence` | PG 행 또는 문서와의 연결 |
| 예외 처리 | `unanswerable`, `ambiguity`, `answer_mode` | 거부·재질문·경고 여부 |
| 분류 | 12개 taxonomy 속성 | slice별 성능 분석 기준 |
| 누수 방지 | `split`, `group_id`, `leakage_group_ids` | 연결된 캠페인이 다른 split에 섞이지 않게 함 |
| 검수 | `validation_status`, `reviewer_notes`, `tags` | 자동 검증과 사람 검수 상태 관리 |

예를 들어 “C0001의 지난주 ROAS를 알려줘”는 질문 문자열뿐 아니라 캠페인 범위,
기간, 지표, 정확한 값과 단위, 해당 값의 PG 원본 행까지 하나의 사례에 포함한다.

## 7. Taxonomy: 결과를 나누어 보는 12개 축

[`taxonomy.yaml`](taxonomy.yaml)은 검색 방법을 지정하는 파일이 아니라, 같은
600건을 마케팅 업무·난이도·근거·위험별로 나누어 성능을 비교하기 위한
통제어휘다. `risk_types`만 복수 선택이고 나머지 11개 축은 사례마다 하나만 갖는다.

| 축 | 구분하는 내용 | 현재 예시 |
| --- | --- | --- |
| `marketing_domain` | 마케팅 의사결정 영역 | 크리에이티브, 예산, 전환, 측정 품질 |
| `analysis_task` | 필요한 분석 작업 | 조회, 집계, 비교, 진단, 권고 |
| `business_objective` | 캠페인 사업 목표 | 인지도, 획득, 리드, 재구매 |
| `funnel_stage` | 고객 여정 단계 | 인지, 고려, 전환, 전 구간 |
| `metric_family` | 핵심 지표 묶음 | 도달, 트래픽, 비용, 전환, ROAS |
| `scope_type` | 조회 범위 | 단일 캠페인, 플랫폼, 기간, 다중 근거 |
| `temporal_granularity` | 시간 단위 | 일, 주, 월, 비교 기간 |
| `difficulty` | 최소 검색·추론 난이도 | L1 단일 사실 ~ L5 모호·공격적 요청 |
| `evidence_type` | 정답 근거 위치 | PG 엔터티·지표·관측, 문서, 복합, 부재 |
| `answer_mode` | 기대하는 답변 행위 | 숫자, 비교, 설명, 재질문, 거부, 경고 |
| `language_style` | 질문 표현 방식 | 전문 한국어, 구어체, 한영 혼합, 오타 |
| `risk_types` | 잘못 답할 위험 | 통화·기간·귀속 불일치, 추적 누락 |

<details>
<summary>12개 축의 현재 전체 개수 보기</summary>

- `marketing_domain`: 엔터티 관리 140, 크리에이티브 성과 120, 예산 집행 91,
  트래픽·참여 72, 도달·인지 62, 측정 품질 60, 전환·획득 33, 매출·수익성 22
- `analysis_task`: 지표 조회 100, 엔터티 식별 90, 원인 진단 50, 권고 50,
  근거 경계 40, 기간 비교 40, 집계·이상 탐지·캠페인 비교·목표 페이싱·
  No-answer·플랫폼 비교·추세 각 30, clarification 20
- `business_objective`: 인지도 100, 리타게팅 95, 리텐션 96, 리드 91,
  획득 84, 앱 성장 84, 알 수 없음 50
- `funnel_stage`: 전 구간 251, 해당 없음 140, 고려 82, 전환 65, 인지 62
- `metric_family`: 없음 120, 비용 118, 트래픽·참여 99, 엔터티 메타데이터 90,
  도달 62, 전환 효율 59, 데이터 품질 30, 가치·수익 22
- `scope_type`: 캠페인·기간 110, 캠페인·플랫폼·일 100,
  캠페인·플랫폼·기간 100, 엔터티 단독 90, 다중 근거 70,
  누락·모호 50, 캠페인 간 비교 40, 플랫폼 간 비교 40
- `temporal_granularity`: 주 140, 캠페인 전체 100, 일 100, 없음 90,
  비교 기간 70, 미지정 70, 월 30
- `difficulty`: L1 90, L2 100, L3 180, L4 130, L5 100
- `evidence_type`: PG 지표 280, PG 엔터티 90, 문서 passage 80,
  PG+문서 50, 근거 없음 기대 40, 부재 증명 30, PG observation 30
- `answer_mode`: 숫자 사실 130, 근거 기반 설명 130, 비교 90,
  엔터티 정보 90, 거부 70, 데이터 품질 경고 40, 추세 30, 재질문 20
- `language_style`: 전문 한국어 287, 한영 혼합 140, 구어체 120,
  오타·노이즈 30, 짧은 키워드 23
- `risk_types`: 위험 없음 470, 불충분한 근거 30, 존재하지 않는 엔터티 30,
  추적 누락 30, 엔터티 모호성 20, 근거 없는 인과 단정 20,
  귀속·통화·기간 불일치 각 10. 이 축은 복수 선택이므로 합계가 600을 넘을 수 있다.

</details>

사람이 읽는 상세 정의와 포함·제외 기준은
[`TAXONOMY.ko.md`](TAXONOMY.ko.md), 기계 판독용 전체 분포는
[`validation/taxonomy_coverage.json`](golden/golden-v1/validation/taxonomy_coverage.json)에
있다.

## 8. 데이터 분할과 누수 방지

| Split | 전체 사례 | 문서 검색 사례 | 용도 |
| --- | ---: | ---: | --- |
| Tune | 364 | 78 | 청킹·Retriever 후보 탐색과 가중치 조정 |
| Validation | 117 | 26 | 후보 간 최종 선택 |
| Holdout | 119 | 26 | 선택 완료 후 한 번만 최종 검증 |

분할 비율은 약 60/20/20이지만 사례 수가 정확히 그 비율은 아니다. 동일 캠페인과
연결된 근거 묶음을 하나의 leakage group으로 유지해 서로 다른 split에 섞이지
않도록 했기 때문이다. Holdout 결과를 보고 설정을 수정하면 해당 Holdout은 더
이상 최종 검증셋이 아니므로 다음 버전에서는 `holdout-v2`가 필요하다.

## 9. 자동 검증과 사람 검수 상태

생성 시 다음 오류가 0건인지 자동 검사한다.

- 중복 `case_id`와 중복 정규화 질문
- 존재하지 않는 corpus 참조
- 잘못된 문서 문자 범위와 passage 불일치
- 공식과 다른 CTR·CVR·CPC·CPA·ROAS 값
- split 간 캠페인 근거 누수
- taxonomy 누락·알 수 없는 코드·규칙 위반
- PII 노출과 근거 없는 positive answer

자동 검증은 데이터 구조와 계산의 일관성을 확인할 뿐 마케팅 판단의 정답성을
보장하지 않는다.

| 검수 상태 | 개수 | 의미 |
| --- | ---: | --- |
| `auto_validated` | 340 | 정확한 엔터티·수치·공식으로 자동 대조 가능 |
| `needs_review` | 260 | No-answer, 모호성, 진단, 권고, 인과 경계 등을 전문가가 확인해야 함 |

따라서 v1은 **실험 파이프라인과 합성 환경의 상대 비교에는 사용 가능**하지만,
실제 마케터 질문에 대한 운영 모델 선택용 완성 Golden으로 간주하면 안 된다.
우선 검수 대상 260건을 마케터 2인이 독립 검수하고, 실제 또는 전문가 작성 질문을
추가한 뒤 새로운 Validation·Holdout으로 다시 평가해야 한다.

## 10. 폴더 구조

```text
evals/
├─ taxonomy.yaml                 # 분류 코드와 규칙
├─ TAXONOMY.ko.md                # 사람이 읽는 taxonomy 설명
├─ golden/golden-v1/
│  ├─ manifest.json              # 버전, 개수, 해시, 전체 분포
│  ├─ data_audit.json            # PG·문서 원본 데이터 감사 결과
│  ├─ corpus/
│  │  ├─ documents.jsonl         # BRIEF·MEMO·ANALYSIS 900개
│  │  └─ observations.jsonl      # 검색·평가용 PG 관측 근거
│  ├─ queries/cases.jsonl        # 실제 평가 질문 600개
│  ├─ judgments/
│  │  ├─ qrels.jsonl             # 질문과 정답 근거의 관련도
│  │  └─ gold_spans.jsonl        # 문서 정답의 정확한 문자 범위 130개
│  ├─ splits/splits.json         # Tune·Validation·Holdout 배정
│  ├─ review/                    # 사람 검수용 CSV와 검수 대기 목록
│  └─ validation/                # 자동 검증과 taxonomy coverage 결과
└─ experiments/                  # 청킹·Retriever 조합과 결과 문서
```

## 11. 재생성과 관련 문서

```bash
launchpilot-build-golden \
  --database-url postgresql://launchpilot:launchpilot-local@localhost:55432/launchpilot \
  --output evals/golden/golden-v1
```

- 데이터 정책: [`dataset_policy.md`](golden/golden-v1/dataset_policy.md)
- 전체 manifest: [`manifest.json`](golden/golden-v1/manifest.json)
- 자동 검증 결과: [`validation_report.json`](golden/golden-v1/validation/validation_report.json)
- 검색 실험 결과: [`experiments/README.md`](experiments/README.md)

Golden 버전을 바꿀 때는 질문만 수정하지 않고 corpus hash, taxonomy snapshot,
qrels, split, 검수 상태를 함께 기록해야 한다. 그래야 이전 실험과 새 실험의 차이가
모델 변경 때문인지 Dataset 변경 때문인지 구분할 수 있다.
