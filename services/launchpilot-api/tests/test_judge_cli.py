from pathlib import Path

import pytest

from launchpilot.evaluation.judging.cli import _append_checkpoint, _load_checkpoint
from launchpilot.evaluation.judging.materialize import (
    SpecificationAdjudicationOutcome,
)
from launchpilot.evaluation.judging.spec_adjudicator import AdjudicationDecision


def test_adjudication_checkpoint_is_source_bound_and_resumable(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.jsonl"
    fingerprint = "sha256:" + "a" * 64
    outcome = SpecificationAdjudicationOutcome(
        problem_id="q1",
        decision=AdjudicationDecision.NEEDS_REVIEW,
        reason="fixture",
    )
    _append_checkpoint(path, fingerprint, outcome)

    assert _load_checkpoint(path, fingerprint) == {"q1": outcome}
    with pytest.raises(ValueError, match="different source dataset"):
        _load_checkpoint(path, "sha256:" + "b" * 64)

    _append_checkpoint(path, fingerprint, outcome)
    with pytest.raises(ValueError, match="duplicate checkpoint outcome"):
        _load_checkpoint(path, fingerprint)
