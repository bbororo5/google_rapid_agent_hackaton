# Task-centric evaluation datasets

이 디렉터리는 시스템 구현이 아니라 **풀어야 할 문제와 성공 정의**를 저장한다.

```text
Dataset                         System under test              Run result
Problem + Eval Specification   SQL/BM25/Dense/Graph/...       Answer/trace/cost
```

Dataset에는 expected tool, route, index, embedding 또는 tool sequence를 저장하지 않는다.
문제 특성은 slice 분석용 explanatory variable이며 특정 route의 정답이 아니다.

## Canonical layout

```text
<dataset>/
├─ manifest.json
├─ world/manifest.json
├─ problems/problems.jsonl
├─ specifications/eval-specifications.jsonl
├─ judgments/evidence-assessments.jsonl
└─ references/answer-examples.jsonl
```

- `world`: 모든 시스템에 동일하게 주어지는 corpus/fact snapshot. Index와 graph
  projection은 여기에 속하지 않는다.
- `problems`: 사용자 발화, information need, 사전에 제공된 context, provenance와
  분석 slice. 성공 기준은 포함하지 않는다.
- `specifications`: answerability, required facts, expected behavior. Tool 사용법은
  포함하지 않는다.
- `judgments`: 현재까지 사람이 보거나 이관한 evidence 판단. 목록에 없는 evidence는
  `unjudged`이며 irrelevant가 아니다.
- `references`: 선택적 답변 예시. `grading_authority=false`인 예시는 정답 ontology가
  아니며 grader 입력으로 사용하지 않는다.

## Current dataset

`marketing-ops-task-v1`은 archived V1/V2가 아니라 `golden-v3` 합성 fixture만을
task-centric 계약으로 이관한 **frontier draft**다. 모든 specification은
`needs_review`, 모든 legacy answer는 `grading_authority=false`이고 release decision은
금지되어 있다.

재생성 명령:

```bash
python evals/migrate_v3_to_task_dataset.py
```

스크립트는 기존 출력이 있으면 덮어쓰지 않는다. 이관 기준을 변경할 때 dataset version을
올리고 새 디렉터리를 생성한다.
