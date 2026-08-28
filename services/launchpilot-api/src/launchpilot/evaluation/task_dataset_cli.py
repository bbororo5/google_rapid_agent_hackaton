from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from launchpilot.evaluation.contracts import ReviewStatus
from launchpilot.evaluation.task_dataset import (
    load_task_dataset,
    verify_world_artifacts,
)


def inspect_task_dataset(root: Path) -> dict[str, object]:
    dataset = load_task_dataset(root)
    verify_world_artifacts(root, dataset.world)
    review_counts = Counter(
        specification.review_status.value
        for specification in dataset.specifications
    )
    source_counts = Counter(problem.source.value for problem in dataset.problems)
    portfolio_counts = Counter(
        problem.portfolio.value for problem in dataset.problems
    )
    blockers = []
    if not dataset.manifest.release_ready:
        blockers.append("manifest.release_ready=false")
    if review_counts[ReviewStatus.NEEDS_REVIEW.value]:
        blockers.append(
            f"{review_counts[ReviewStatus.NEEDS_REVIEW.value]} specifications need review"
        )
    if not source_counts.get("production", 0):
        blockers.append("no production-sourced problems")

    return {
        "dataset_id": dataset.manifest.dataset_id,
        "dataset_version": dataset.manifest.dataset_version,
        "fingerprint": f"sha256:{dataset.fingerprint}",
        "world_id": dataset.world.world_id,
        "counts": {
            "problems": len(dataset.problems),
            "specifications": len(dataset.specifications),
            "evidence_judgments": len(dataset.evidence_judgments),
            "reference_answers": len(dataset.reference_answers),
        },
        "review_statuses": dict(sorted(review_counts.items())),
        "problem_sources": dict(sorted(source_counts.items())),
        "portfolios": dict(sorted(portfolio_counts.items())),
        "release_ready": dataset.manifest.release_ready and not blockers,
        "release_blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate task-centric eval artifacts and report release blockers."
    )
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            inspect_task_dataset(args.dataset),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
