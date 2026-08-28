from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from launchpilot.evaluation.contracts import (  # noqa: E402
    Answerability,
    EvalSpecification,
    EvidenceAssessment,
    EvidenceJudgment,
    ExpectedBehavior,
    GraderKind,
    InformationModality,
    PortfolioRole,
    ProblemProvenance,
    ProblemRecord,
    QueryCharacteristics,
    QuerySource,
    RequiredFact,
    ReviewStatus,
    SourceCardinality,
    SuppliedContext,
    TaskShape,
)
from launchpilot.evaluation.task_dataset import (  # noqa: E402
    EvidenceJudgmentRecord,
    ReferenceAnswerRecord,
    TaskDatasetManifest,
    WorldArtifact,
    WorldManifest,
    load_task_dataset,
    verify_world_artifacts,
)

SOURCE_ROOT = ROOT / "evals" / "golden" / "golden-v3"
OUTPUT_ROOT = ROOT / "evals" / "datasets" / "marketing-ops-task-v1"
WORLD_ID = "synthetic-marketing-ops-v3"

_TASK_NEEDS = {
    "copy_fatigue_action": (
        "해당 캠페인의 헤드라인 반응 저하와 그에 대응한 카피 변경 기록을 확인한다.",
        TaskShape.LOOKUP,
        (InformationModality.UNSTRUCTURED, InformationModality.RELATIONAL),
    ),
    "pacing_cut_action": (
        "해당 캠페인의 예산 소진 이상과 실제 페이싱 조치 기록을 확인한다.",
        TaskShape.LOOKUP,
        (InformationModality.MIXED, InformationModality.RELATIONAL),
    ),
    "brief_guideline_lookup": (
        "해당 캠페인의 초기 페이싱 운영 원칙과 개입 기준을 확인한다.",
        TaskShape.LOOKUP,
        (InformationModality.UNSTRUCTURED,),
    ),
    "video_fatigue_action": (
        "해당 캠페인의 영상 소재 피로 대응 조치가 실제로 있었는지 확인한다.",
        TaskShape.LOOKUP,
        (InformationModality.UNSTRUCTURED, InformationModality.RELATIONAL),
    ),
    "cross_campaign_comparison": (
        "질문이 지정한 범위에서 배너 성과 저하 대응 사례들을 찾아 비교한다.",
        TaskShape.COMPARISON,
        (InformationModality.UNSTRUCTURED, InformationModality.RELATIONAL),
    ),
    "negative_rejection": (
        "요청한 집행이나 문서가 현재 평가 world에 존재하는지 확인한다.",
        TaskShape.LOOKUP,
        (InformationModality.UNSTRUCTURED,),
    ),
}


def migrate(source_root: Path = SOURCE_ROOT, output_root: Path = OUTPUT_ROOT) -> Path:
    if output_root.exists():
        raise FileExistsError(f"task dataset already exists: {output_root}")

    cases = _jsonl(source_root / "queries" / "cases.jsonl")
    qrels = _jsonl(source_root / "judgments" / "qrels.jsonl")
    truths = _jsonl(source_root / "judgments" / "generation_ground_truth.jsonl")
    documents = _jsonl(source_root / "corpus" / "documents.jsonl")
    splits = json.loads(
        (source_root / "splits" / "splits.json").read_text(encoding="utf-8")
    )["cases"]

    truth_by_id = _unique(truths, "case_id")
    document_by_id = _unique(documents, "id")
    split_by_id = {
        case_id: split_name
        for split_name, case_ids in splits.items()
        for case_id in case_ids
    }
    qrels_by_case: dict[str, list[Mapping[str, Any]]] = {}
    for qrel in qrels:
        qrels_by_case.setdefault(str(qrel["case_id"]), []).append(qrel)

    problems: list[ProblemRecord] = []
    specifications: list[EvalSpecification] = []
    judgments: list[EvidenceJudgmentRecord] = []
    references: list[ReferenceAnswerRecord] = []

    for case in cases:
        problem_id = str(case["case_id"])
        task = str(case["analysis_task"])
        truth = truth_by_id[problem_id]
        if task not in _TASK_NEEDS:
            raise ValueError(f"unknown analysis_task: {task}")
        information_need, task_shape, modalities = _TASK_NEEDS[task]
        is_negative = bool(case.get("is_negative", False))
        legacy_split = split_by_id.get(problem_id)
        supplied_context = _supplied_context(case, task)

        problems.append(
            ProblemRecord(
                problem_id=problem_id,
                user_utterance=str(case["query"]),
                information_need=information_need,
                world_id=WORLD_ID,
                supplied_context=supplied_context,
                source=QuerySource.SYNTHETIC,
                portfolio=PortfolioRole.FRONTIER,
                characteristics=QueryCharacteristics(
                    modalities=modalities,
                    lexical_need="paraphrase_gap",
                    entity_centric=task != "cross_campaign_comparison",
                    hop_count=2 if task == "cross_campaign_comparison" else 1,
                    task_shape=task_shape,
                    source_cardinality=(
                        SourceCardinality.MULTIPLE
                        if task == "cross_campaign_comparison"
                        else SourceCardinality.UNKNOWN
                        if is_negative
                        else SourceCardinality.SINGLE
                    ),
                    tags=(f"legacy_task:{task}",),
                ),
                leakage_group_ids=tuple(
                    sorted(
                        {
                            f"template:{task}",
                            f"campaign:{case['campaign_ref']}",
                        }
                    )
                ),
                provenance=ProblemProvenance(
                    source_dataset="golden-v3",
                    source_record_id=problem_id,
                    generation_method="synthetic_persona_then_mechanical_rewrite",
                    legacy_split=legacy_split,
                ),
            )
        )

        required_facts = _required_facts(task, truth, document_by_id)
        expected_behaviors = (
            (ExpectedBehavior.ABSTAIN,)
            if is_negative
            else (ExpectedBehavior.ANSWER,)
        )
        specification = EvalSpecification(
            spec_id=f"{problem_id}.spec",
            spec_version="v1-draft",
            problem_id=problem_id,
            answerability=(
                Answerability.INSUFFICIENT_EVIDENCE
                if is_negative
                else Answerability.ANSWERABLE
            ),
            required_facts=required_facts,
            expected_behaviors=expected_behaviors,
            review_status=ReviewStatus.NEEDS_REVIEW,
            grader_rubric_version=(
                "task-required-facts-v1-draft" if required_facts else None
            ),
        )
        specifications.append(specification)

        supported_fact_ids = (
            ()
            if task == "cross_campaign_comparison"
            else tuple(fact.fact_id for fact in required_facts)
        )
        for qrel in qrels_by_case.get(problem_id, ()):
            judgments.append(
                EvidenceJudgmentRecord(
                    problem_id=problem_id,
                    assessment=EvidenceAssessment(
                        evidence_ref=str(qrel["corpus_ref"]),
                        judgment=EvidenceJudgment.KNOWN_RELEVANT,
                        relevance_grade=int(qrel.get("relevance", 1)),
                        supports_fact_ids=supported_fact_ids,
                        rationale=(
                            "Legacy V3 known-positive seed. Human review is pending; "
                            "absence of other evidence means unjudged."
                        ),
                    ),
                )
            )

        references.append(
            ReferenceAnswerRecord(
                problem_id=problem_id,
                answer=str(truth["canonical_gold_answer"]),
                status="legacy_synthetic_example",
                grading_authority=False,
                provenance="golden-v3/generation_ground_truth.jsonl",
            )
        )

    world = _world_manifest(source_root, output_root)
    manifest = TaskDatasetManifest(
        dataset_id="marketing-ops-task",
        dataset_version="v1-draft",
        lifecycle="frontier",
        release_ready=False,
        source_fixture="golden-v3",
        world_id=WORLD_ID,
        problem_count=len(problems),
        specification_count=len(specifications),
        evidence_judgment_count=len(judgments),
        reference_answer_count=len(references),
        human_review_status="awaiting_human_review",
        prohibited_uses=(
            "architecture_release_decision",
            "production_capability_claim",
            "treating_legacy_reference_answers_as_complete_truth",
            "treating_unlisted_evidence_as_irrelevant",
        ),
    )

    _write_json(output_root / "manifest.json", manifest.model_dump(mode="json"))
    _write_json(output_root / "world" / "manifest.json", world.model_dump(mode="json"))
    _write_jsonl(output_root / "problems" / "problems.jsonl", problems)
    _write_jsonl(
        output_root / "specifications" / "eval-specifications.jsonl",
        [
            specification.model_dump(
                mode="json", exclude={"evidence_assessments"}
            )
            for specification in specifications
        ],
    )
    _write_jsonl(
        output_root / "judgments" / "evidence-assessments.jsonl", judgments
    )
    _write_jsonl(output_root / "references" / "answer-examples.jsonl", references)

    dataset = load_task_dataset(output_root)
    verify_world_artifacts(output_root, dataset.world)
    return output_root


def _required_facts(
    task: str,
    truth: Mapping[str, Any],
    document_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[RequiredFact, ...]:
    if bool(truth.get("is_negative", False)):
        return ()
    if task == "brief_guideline_lookup":
        document_ids = tuple(str(item) for item in truth["expected_document_ids"])
        descriptions = [
            _clean_document_content(str(document_by_id[item]["content"]))
            for item in document_ids
            if item in document_by_id
        ]
        return (
            RequiredFact(
                fact_id="operating_guideline",
                description=(
                    "초기 운영 지침의 핵심 내용: " + " ".join(descriptions)
                ),
                grader=GraderKind.HUMAN,
            ),
        )
    if task == "cross_campaign_comparison":
        return (
            RequiredFact(
                fact_id="comparison_coverage",
                description=(
                    "질문이 지정한 범위에서 해당 조치를 수행한 캠페인과 근거를 "
                    "빠짐없이 식별한다. 현재 legacy evidence pool은 불완전하다."
                ),
                grader=GraderKind.HUMAN,
            ),
            RequiredFact(
                fact_id="comparison_result",
                description="식별된 캠페인들의 문제 상황과 조치를 비교해 설명한다.",
                grader=GraderKind.HUMAN,
            ),
        )

    triad = truth.get("causal_triad", {})
    return (
        RequiredFact(
            fact_id="trigger",
            description=f"문제 상황: {triad.get('trigger_anomaly', '')}",
            grader=GraderKind.HUMAN,
        ),
        RequiredFact(
            fact_id="action",
            description=f"실행된 조치: {triad.get('action_decision', '')}",
            grader=GraderKind.HUMAN,
        ),
    )


def _supplied_context(
    case: Mapping[str, Any], task: str
) -> tuple[SuppliedContext, ...]:
    if task == "cross_campaign_comparison":
        return (SuppliedContext(key="workspace_scope", value="all_campaigns"),)
    return (
        SuppliedContext(
            key="active_campaign_ref", value=str(case["campaign_ref"])
        ),
        SuppliedContext(key="brand", value=str(case["brand"])),
    )


def _world_manifest(source_root: Path, output_root: Path) -> WorldManifest:
    roles = {
        "documents": source_root / "corpus" / "documents.jsonl",
        "structured_observations": source_root / "corpus" / "observations.jsonl",
        "semantic_relation_annotations": source_root / "corpus" / "edges.jsonl",
    }
    artifacts = []
    for role, path in roles.items():
        relative = Path(os.path.relpath(path, output_root))
        artifacts.append(
            WorldArtifact(
                role=role,
                path=relative.as_posix(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                record_count=sum(
                    1
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ),
            )
        )
    return WorldManifest(
        world_id=WORLD_ID,
        world_version="v3-snapshot",
        source_type="synthetic",
        description=(
            "Controlled synthetic marketing operations world inherited from golden-v3. "
            "It is a harness fixture, not a production distribution sample."
        ),
        artifacts=tuple(artifacts),
        representation_notes=(
            "Documents and observations are canonical world inputs.",
            "Semantic relation annotations describe known relations but do not require a graph tool.",
            "Indexes, embeddings, retrieval routes, and tool descriptions belong to the system under test.",
        ),
    )


def _clean_document_content(value: str) -> str:
    return re.sub(r"^\[C\d{4}\]\s*", "", value).strip()


def _jsonl(path: Path) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _unique(
    rows: Sequence[Mapping[str, Any]], key: str
) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = str(row[key])
        if value in output:
            raise ValueError(f"duplicate {key}: {value}")
        output[value] = row
    return output


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Sequence[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                row.model_dump(mode="json")
                if hasattr(row, "model_dump")
                else row,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    print(migrate())
