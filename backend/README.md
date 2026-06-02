# LaunchPilot Backend (Java Business Backend)

C4 `Business Backend (Java 21 / Spring Boot)` 컨테이너. 프론트 ↔ Python ↔ Elastic 3개를 잇는 게이트웨이 hub.

설계: [`DESIGN.md`](./DESIGN.md). 계약: `../contracts/01,02,03`.

## 스택

- Java 21 (Gradle toolchain 자동 프로비저닝), Spring Boot 3.3
- Elasticsearch Java Client 8.15 (계약 03 쓰기)
- RestClient (계약 02 Python 호출)
- 테스트: JUnit5 + 실 Elastic Cloud + WireMock(Python 스텁)

## 빌드

```sh
gradle build            # 컴파일 + 테스트 (creds 없으면 e2e skip)
gradle compileTestJava  # 컴파일만
gradle bootRun          # 앱 기동
```

## 환경변수

| 변수 | 용도 | 필수 |
| --- | --- | --- |
| `ELASTIC_URL` | Elastic Cloud 엔드포인트 (예: `https://xxx.es.region.gcp.elastic.cloud:443`) | 앱 기동/e2e 필수 |
| `ELASTIC_API_KEY` | Elastic API Key (쓰기 권한) | 권장 |
| `AGENT_SERVICE_URL` | Python 인프라 base URL (기본 `http://localhost:8000`) | 선택 |

`ELASTIC_URL` 미설정 시: ES 빈 비활성(앱 기동 불가), e2e 테스트는 graceful skip.

PowerShell 예:
```powershell
$env:ELASTIC_URL = "https://...elastic.cloud:443"
$env:ELASTIC_API_KEY = "..."
gradle bootRun
```

## 엔드포인트 (계약 01)

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| POST | `/api/import/csv` | CSV → `content_posts` 색인. 201 |
| POST | `/api/agent/run` | 에이전트 비동기 트리거. 202 PENDING |
| GET | `/api/agent/runs/{id}` | 폴링 (Python 중계). 200 |
| POST | `/api/agent/actions/{id}/approve` | 승인 → `growth_briefs`+`calendar_events` 적재. 200 |

## 인덱스 부트스트랩

기동 시 `content_posts`, `growth_briefs`, `calendar_events` 없으면 계약 03 매핑으로 자동 생성 (멱등).

## e2e 테스트

`src/test/java/.../e2e/MainAnalysisApprovalE2ETest.java` — `scenarios/main-analysis-approval.scenario.json` 흐름.
Python = WireMock(계약 02 픽스처), Elastic = 실 클라우드. 매 실행 유니크 workspace로 격리, teardown에서 `delete_by_query`.

```sh
# ELASTIC_URL/ELASTIC_API_KEY 설정 후
gradle test --tests "*MainAnalysisApprovalE2ETest"
```
</content>
