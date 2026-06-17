# phases — 라운드 실행기

한 단계(phase)를 한 번 실행하는 일을 "라운드"라 부른다. 단계마다 러너 파일이
하나씩 있어서, 파일명만 봐도 무슨 라운드인지 읽힌다.

## 단계 흐름

```
분석(analysis) ──▶ 가설(hypothesis) ──▶ 계획(plan) ──▶ 평가(eval, 미구현)
  신호 찾기          원인 가설            실험계획+승인
```

각 러너의 `run()` 은 위에서 아래로 읽으면 줄거리가 되도록 짰다. 예(분석):

```python
self.check_cancelled(turn)              # 취소됐으면 멈춤
await self._announce_start(turn)        # 시작 알림
signals = await self._detect_signals(turn)   # 신호 찾기
if not signals:
    return await self._report_no_signals(turn)
await self._save_signals(turn, signals) # 저장
await self._show_signals(turn, signals) # 보여주기
```

## 파일 한눈에

| 파일 | 한 줄 역할 |
|---|---|
| [analysis.py](analysis.py) | 분석 라운드 — 지표에서 두드러진 신호 찾기 |
| [hypothesis.py](hypothesis.py) | 가설 라운드 — 신호의 원인을 가설로 |
| [plan.py](plan.py) | 계획 라운드 — 실험 계획 작성 + 가드레일 + 승인 요청 |
| [unsupported.py](unsupported.py) | 평가 라운드 — 아직 미구현, 안내만 |
| [base.py](base.py) | 공통 토대 — 세 라운드가 공유하는 저장/불러오기/취소 |
| [windows.py](windows.py) | 분석 기간 계산 (최근 7일 / 직전 28일 기준선) |
| [registry.py](registry.py) | 단계 선택표 — phase 값으로 러너 객체를 꺼냄 (if 없음) |

## 중복을 줄인 방법

세 라운드가 똑같이 반복하던 두 가지를 base.py 공통 헬퍼로 모았다:

- `_load_saved(...)` : 이전 단계가 저장한 결과물을 모델로 되살리기
- `_save_round_result(...)` : 결과물을 상태+저장소에 보관하고 진행상황 알리기

> 단계가 늘면? registry.py 에 한 줄 추가 + 러너 파일 하나 추가. 다른 데는 안 건드림.
