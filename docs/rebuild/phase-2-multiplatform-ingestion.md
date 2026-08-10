# Phase 2 Multi-platform Ads Ingestion

> 상태: **확정**
>
> 목적: 여러 광고 플랫폼의 외부 Campaign을 하나의 LaunchPilot Campaign 관점에서 수집한다.

## Product boundary

- Google Ads와 Meta Ads가 유료 광고 성과의 핵심 데이터 소스다.
- YouTube Analytics는 채널·콘텐츠 성과를 제공하는 보조 맥락이다.
- LaunchPilot `Campaign`은 플랫폼 독립적인 업무 단위이며 외부 Campaign ID와 동일하지 않다.
- 사용자가 분석을 요청할 때 데이터를 가져오고 예약 수집은 하지 않는다.

## Delivery slices

| 단계 | 결과 |
| --- | --- |
| 2A | 공통 Connector 계약과 플랫폼 독립 DTO |
| 2B | YouTube Analytics 인증·수집 경로 |
| 2C | Google Ads 계정·Campaign·성과 수집 |
| 2D | Meta Ads 계정·Campaign·성과 수집 |
| 2E | 외부 Campaign 연결과 멀티플랫폼 Observation 조립 |

## Implementation status

| 단계 | 상태 | 검증 |
| --- | --- | --- |
| 2A | 완료 | 공통 Connector contract 테스트 |
| 2B | 완료 | 실제 Google 계정으로 OAuth·채널·Analytics E2E 성공 |
| 2C | 구현 완료 | REST v25 fixture 성공, Developer Token 기반 실제 계정 검증 대기 |
| 2D | 구현 완료 | Graph API fixture 성공, Meta 앱 기반 실제 계정 검증 대기 |
| 2E | 구현 완료 | complete·partial·all-failed 조립 테스트 |

수집 결과는 Observation → PlatformSlice → MetricObservation의 관계형 구조로 PostgreSQL에 영속화한다. SQLite로 검증했던 Phase 2 구현은 [ADR-0002](adr/0002-source-of-truth-database.md)에 따라 PostgreSQL로 전환했다. 서버를 재시작해도 Campaign, Conversation, Observation과 출처 정보가 유지되며 구조화 Retrieval 입력으로 사용한다.

## Connector contract

각 광고 Connector는 다음 기능을 제공한다.

```text
list_accounts(access_token)
list_campaigns(access_token, account_ref)
fetch_campaign_metrics(access_token, account_ref, campaign_ref, period)
```

Connector는 플랫폼 원본 응답을 `ExternalAccount`, `ExternalCampaign`, `PlatformSlice`로 결정적으로 변환한다. LLM은 이 변환 과정에 개입하지 않는다.

## Metric policy

- 비교 가능한 지표는 `spend`, `impressions`, `clicks`, `conversions`, `conversion_value` 같은 canonical key로 정규화한다.
- 플랫폼 고유 의미가 있는 지표는 원본 의미를 잃지 않도록 별도 key로 보존한다.
- 통화, 계정 시간대, attribution 설정을 함께 보존한다.
- 서로 다른 attribution 조건의 conversion을 동일 수치처럼 합산하지 않는다.

## Completion criteria

- Google Ads와 Meta Ads 계정을 연결할 수 있다.
- 각 플랫폼의 광고 Campaign을 조회하고 LaunchPilot Campaign에 연결할 수 있다.
- 같은 기간의 두 플랫폼 성과를 하나의 `CampaignObservation`으로 생성한다.
- 일부 플랫폼 실패 시 성공한 Slice를 보존하고 실패 사유를 `PARTIAL`로 기록한다.
- Access/Refresh Token을 암호화해 저장하고 만료된 토큰을 갱신한다.
- 실제 계정 또는 재현 가능한 fixture로 각 Connector의 정규화 계약을 검증한다.
