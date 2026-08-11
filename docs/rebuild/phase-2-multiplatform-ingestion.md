# Phase 2 — Identity & Multi-platform Ingestion

> 상태: **mock E2E 완료 · 실제 Ads 계정 검증 대기**

이 단계는 사용자가 승인한 외부 계정의 Campaign을 LaunchPilot Campaign에 연결하고, 플랫폼별 응답을 하나의 불변 Observation으로 수집한다.

## Boundary and flow

- Google Ads와 Meta Ads는 유료 광고 성과, YouTube Analytics는 소유 채널 콘텐츠 맥락을 제공한다.
- LaunchPilot Campaign과 외부 Campaign ID는 동일하지 않으며 binding으로 연결한다.
- 예약 수집 없이 사용자의 분석 요청 시 데이터를 가져온다.

```text
Google 로그인
→ 플랫폼별 OAuth 승인
→ 외부 계정·Campaign 선택
→ LaunchPilot Campaign binding
→ 같은 기간 데이터 수집
→ CampaignObservation 저장
```

## Connector contract

```text
list_accounts(access_token)
list_campaigns(access_token, account_ref)
fetch_campaign_metrics(access_token, account_ref, campaign_ref, period)
```

Connector가 원본 응답을 `ExternalAccount`, `ExternalCampaign`, `PlatformSlice`로 결정적으로 정규화한다. LLM은 이 과정에 개입하지 않는다.

공통 지표는 `spend`, `impressions`, `clicks`, `conversions`, `conversion_value`로 정규화하되 통화·시간대·attribution과 원본 의미를 보존한다. attribution 조건이 다른 conversion은 같은 수치처럼 합산하지 않는다.

## Failure and security rules

- Access/Refresh Token은 암호화하고 만료된 Access Token은 갱신한다.
- 일부 플랫폼 실패 시 성공한 Slice와 실패 사유를 `PARTIAL`로 저장한다.
- 모두 실패하면 빈 Observation을 만들지 않는다.
- 최신 수집은 기존 Snapshot을 덮어쓰지 않는다.

## Verification

| 범위 | 상태 |
| --- | --- |
| Google 로그인·YouTube OAuth/Analytics | 실제 계정 E2E 완료 |
| Google Ads | REST fixture 완료, Developer Token 실제 계정 검증 대기 |
| Meta Ads | Graph API fixture 완료, 실제 광고 자산 검증 대기 |
| 다중 플랫폼 조립 | complete·partial·all-failed 테스트 완료 |

수집 결과는 PostgreSQL의 Structured Retrieval 원본이 된다. 다음 단계는 수치와 문서를 검색하는 [Retrieval Evolution Plan](retrieval-evolution-plan.md)이다.
