# Marketing Retrieval Evaluation Taxonomy

`taxonomy.yaml`은 Golden Dataset 질문을 검색 방식이 아닌 마케팅 의사결정과
평가 난이도 기준으로 분류하는 통제어휘다. 특정 retriever를 정답으로 지정하지
않으며, 실험 결과를 slice별로 비교하기 위한 기준을 제공한다.

## 이론적 기준

- W3C SKOS 방식을 따라 각 개념에 안정적인 코드, 한국어·영문 선호명, 동의어,
  정의, 포함·제외 규칙과 예시를 둔다.
- NIST TREC 방식처럼 corpus, information need/query, qrels, run을 분리한다.
  taxonomy는 query의 정보 요구를 설명하며 qrels나 retriever 설정을 대신하지
  않는다.
- 광고 지표는 Google Ads 공식 metric 정의를 기준으로 delivery, traffic,
  spend, conversion, value/return으로 분리한다.
- 플랫폼 비교에는 통화, 기간, 전환 정의, attribution window가 일치하는지
  확인하는 위험 코드를 둔다.

참조:

- [W3C SKOS Reference](https://www.w3.org/TR/skos-reference/)
- [W3C SKOS Primer](https://www.w3.org/TR/skos-primer/)
- [NIST How To TREC](https://trec.nist.gov/howto.html)
- [Google Ads API Metrics](https://developers.google.com/google-ads/api/reference/rpc/v25/Metrics)
- [Google Ads conversion measurement](https://support.google.com/google-ads/answer/6270625)
- [Google Ads attribution models](https://support.google.com/google-ads/answer/6259715)
- [Meta Conversions API](https://www.facebook.com/business/help/AboutConversionsAPI)

## 필수 분류 축

| 축 | 판정 질문 | 예시 |
| --- | --- | --- |
| `marketing_domain` | 어떤 마케팅 의사결정을 다루는가? | 전환·고객획득 |
| `analysis_task` | 어떤 분석 연산이나 판단이 필요한가? | 플랫폼 비교 |
| `business_objective` | 캠페인의 사업 목표는 무엇인가? | 신규 고객 확보 |
| `funnel_stage` | 주로 어느 고객 여정 단계인가? | 전환 |
| `metric_family` | 핵심 지표 묶음은 무엇인가? | 전환·획득효율 |
| `scope_type` | 엔터티와 필터 범위는 무엇인가? | 캠페인·플랫폼·기간 |
| `temporal_granularity` | 시간 분석 단위는 무엇인가? | 주간 |
| `difficulty` | 최소 검색·추론 복잡도는 얼마인가? | L3 집계·비교 |
| `evidence_type` | 권위 근거는 어디에 있는가? | PG·문서 결합 |
| `answer_mode` | 정답은 어떤 행위로 표현되는가? | 비교·순위 반환 |
| `language_style` | 사용자의 표면 표현은 어떤가? | 한영 혼합 |
| `risk_types` | 잘못 답할 때 어떤 위험이 있는가? | 어트리뷰션 불일치 |

`risk_types`만 복수 선택이며, 나머지는 사례마다 정확히 하나를 선택한다.

## 난이도 기준

- L1: 단일 엔터티 또는 단일 사실
- L2: 캠페인·플랫폼·날짜·지표가 지정된 필터 조회
- L3: 여러 행의 집계, 파생지표 재계산, 비교 또는 순위
- L4: 엔터티 식별 후 PG와 문서 등 다중 근거 연결
- L5: 모호성, no-answer, 공격적 요구에 대한 clarification 또는 abstention

난이도는 질문 문장의 길이나 전문용어 수가 아니라, 정답을 얻기 위한 최소 연산과
근거 연결 수로 판정한다.

## 사례 수와 운영 기준

카테고리별 사례 수는 통계적 신뢰구간을 대신하지 않는다. 다음 값은 운영 gate다.

- 20개 미만: 탐색적 결과로도 취약
- 20개 이상: 탐색적 리포팅 가능
- 30개 이상: 방향성 판단 가능
- 핵심 slice 50개 이상 및 서로 다른 캠페인 10개 이상: 모델 선택 후보
- 비율 지표는 Wilson 95% 신뢰구간을 함께 보고

전체 평균에 과적합하지 않도록 단일 `analysis_task`와 `marketing_domain`이 전체의
35%를 넘으면 불균형으로 표시한다. 최소 4개 언어 스타일과 4개 난이도 레벨을
요구한다.

이 숫자는 품질을 보장하는 절대 법칙이 아니다. 실제 모델 채택은 holdout 성능,
신뢰구간, slice 최저점, latency와 cost를 함께 판단한다.

## 현재 Golden v1 판정

현재 600개 사례는 분류 무결성에 통과했다. 단일 조회에 더해 다음 영역을
보강했다.

- 집계, 기간·플랫폼·캠페인 비교, 4주 추세
- 추적 누락 이상 탐지
- 통화·어트리뷰션·기간 불일치 안전성 사례
- 문서 원인 진단 50개, 예산 페이싱 30개, PG+문서 권고 50개
- L4 문서·다중근거 사례 130개

다만 production model-selection 전체 coverage에는 아직 미달한다. no-answer,
ambiguous, unsupported-causality 핵심 slice가 현재 20~30개이므로 운영 gate인
50개보다 적다. 합성 문서는 평가 파이프라인용 fixture이므로 실제 마케터 문서로
교체한 뒤 사람 검수를 다시 완료해야 한다.

세부 수치는 `golden/golden-v1/validation/taxonomy_coverage.json`에서 확인한다.
이 결과는 실패를 숨기지 않고 다음 데이터 보강 우선순위를 결정하기 위한 것이다.
