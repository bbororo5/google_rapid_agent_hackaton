# phoenix_export — Phoenix/OpenInference export

Phoenix/Arize로 agent trace와 evaluation trace를 내보내는 외부 연동 컴포넌트다.

이 디렉터리는 evaluation을 실행하지 않는다. evaluation 실행은 `app/eval/`이 맡고, 여기는 Phoenix export 초기화만 담당한다.

## 책임

- `PHOENIX_API_KEY`가 있을 때 Phoenix tracing provider 등록
- OpenInference/ADK auto instrumentation 활성화
- 비활성 또는 실패 시 runtime 흐름을 깨지 않고 no-op으로 동작

## 공개 진입점

| API | 역할 |
|---|---|
| `init_phoenix_export()` | Phoenix tracing provider를 등록하고 provider를 반환 |
