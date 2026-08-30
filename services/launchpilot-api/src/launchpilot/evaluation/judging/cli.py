from __future__ import annotations

import argparse
import json
from pathlib import Path

from launchpilot.evaluation.contracts import Answerability
from launchpilot.evaluation.task_dataset import load_task_dataset

from .config import GeminiJudgeSettings
from .gemini_client import GeminiJudgeClient
from .materialize import (
    SpecificationAdjudicationOutcome,
    materialize_judge_ready_dataset,
)
from .spec_adjudicator import (
    AdjudicationDecision,
    GeminiSpecificationAdjudicator,
    SpecificationAdjudicationRubric,
)
from .world_evidence import WorldEvidenceResolver


def main() -> None:
    parser = argparse.ArgumentParser(description="LaunchPilot Gemini eval judge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="make one structured connectivity call")
    adjudicate = subparsers.add_parser(
        "adjudicate", help="build a machine-adjudicated derived task dataset"
    )
    adjudicate.add_argument("--dataset-root", type=Path, required=True)
    adjudicate.add_argument("--output-root", type=Path, required=True)
    adjudicate.add_argument("--rubric", type=Path, required=True)
    adjudicate.add_argument("--limit", type=int)
    adjudicate.add_argument("--base-seed", type=int, default=1701)
    adjudicate.add_argument(
        "--confirm-live-calls",
        action="store_true",
        help="required because adjudication incurs Vertex AI usage",
    )
    args = parser.parse_args()
    settings = GeminiJudgeSettings.from_environment()
    client = GeminiJudgeClient(settings)
    if args.command == "preflight":
        call = client.preflight()
        print(
            json.dumps(
                {
                    "ok": call.payload.ok,
                    "model": call.metadata.model,
                    "thinking_level": call.metadata.thinking_level,
                    "request_id": call.metadata.request_id,
                    "latency_ms": call.metadata.latency_ms,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    _adjudicate(args, client)


def _adjudicate(args, client: GeminiJudgeClient) -> None:
    dataset = load_task_dataset(args.dataset_root)
    answerable = sorted(
        (
            specification
            for specification in dataset.specifications
            if specification.answerability == Answerability.ANSWERABLE
        ),
        key=lambda item: item.problem_id,
    )
    selected = answerable[: args.limit] if args.limit is not None else answerable
    estimated_calls = len(selected) * 2
    if not args.confirm_live_calls:
        raise SystemExit(
            f"Refusing {estimated_calls} live judge calls without --confirm-live-calls"
        )
    problem_by_id = {problem.problem_id: problem for problem in dataset.problems}
    adjudicator = GeminiSpecificationAdjudicator(
        client=client,
        resolver=WorldEvidenceResolver(args.dataset_root, dataset.world),
        rubric=SpecificationAdjudicationRubric.load(args.rubric),
    )
    selected_ids = {item.problem_id for item in selected}
    outcome_by_id = {}
    for index, specification in enumerate(selected, start=1):
        record = adjudicator.adjudicate(
            problem=problem_by_id[specification.problem_id],
            specification=specification,
            base_seed=args.base_seed + index * 10,
        )
        outcome_by_id[specification.problem_id] = SpecificationAdjudicationOutcome(
            problem_id=specification.problem_id,
            decision=record.decision,
            reason=record.decision_reason,
            record=record,
        )
        print(
            f"[{index}/{len(selected)}] {specification.problem_id}: {record.decision}"
        )
    for specification in dataset.specifications:
        if specification.problem_id in selected_ids:
            continue
        if specification.answerability != Answerability.ANSWERABLE:
            reason = (
                "needs exhaustive-world adjudication; empty qrels do not prove "
                "insufficient evidence"
            )
            decision = AdjudicationDecision.NEEDS_REVIEW
        else:
            reason = "not selected for this adjudication run"
            decision = AdjudicationDecision.NEEDS_REVIEW
        outcome_by_id[specification.problem_id] = SpecificationAdjudicationOutcome(
            problem_id=specification.problem_id,
            decision=decision,
            reason=reason,
        )
    output = materialize_judge_ready_dataset(
        source_root=args.dataset_root,
        source=dataset,
        output_root=args.output_root,
        outcomes=tuple(outcome_by_id.values()),
    )
    print(
        json.dumps(
            {
                "output_root": str(args.output_root),
                "dataset_version": output.manifest.dataset_version,
                "adjudication_status": output.manifest.adjudication_status,
                "fingerprint": "sha256:" + output.fingerprint,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
