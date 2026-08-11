# LaunchPilot Archive

이 디렉터리는 현재 리빌드에서 사용하지 않는 구현과 설계를 보존한다. 과거 판단 과정과 실패·학습 기록을 확인하기 위한 참고 자료이며, 현행 애플리케이션의 계약이 아니다.

## Archive groups

### `google-adk-hackathon-prototype/`

Google ADK Agent, Next.js Frontend, Java Backend, 이전 계약과 E2E·관측 도구를 하나의 역사적 스냅샷으로 보존한다. 당시 제품·아키텍처 문서도 `docs/`에 함께 둔다.

### `superseded-designs/`

해커톤 개발 중 대체된 초기 오케스트레이터 설계와 Phase 0 이전의 명세 초안을 보존한다.

## Usage rule

- 아카이브 코드는 import, 빌드, 테스트, 배포 대상에 포함하지 않는다.
- 과거 문제 정의, 설계 근거와 실패 사례를 확인할 때만 사용한다.
- 아카이브와 현행 문서가 충돌하면 [현행 문서 포털](../docs/README.md)에서 연결하는 결정이 우선한다.
- 현행 구현은 [`services/launchpilot-api/`](../services/launchpilot-api/)에서만 변경한다.
- 아카이브를 수정해 현행화하지 않는다. 새로운 결정은 `docs/rebuild/`에 기록한다.
