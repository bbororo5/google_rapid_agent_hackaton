"""Grounding gate: cited evidence refs/values must match what the tools returned.

Runs in STUB mode (conftest). The stub workers call the real evidence wrapper,
so a capture built around them is the same ground truth the orchestrator sees.
"""
from app.agents import failure, formatter, reviewer, stub
from app.contracts import DateRange, ValidationIssueCode
from app.tools import evidence, seed

_RANGE = DateRange(start="2026-06-04", end="2026-06-10")


def _scope():
    return evidence.scope(seed.WORKSPACE_ID, seed.CAMPAIGN_ID, None, None, None, None)


def _run_stub_pipeline():
    """Stub analyst -> strategist -> writer under one capture, like the orchestrator."""
    with evidence.capture() as cap, _scope():
        signals = stub.analyst("analyze", _RANGE).signals
        hypotheses = stub.strategist(signals).hypotheses
        plan = stub.writer(hypotheses, _RANGE).experiment_plan
    payload = formatter.assemble(signals, hypotheses, plan)
    return payload, cap.snapshot()


def _codes(report):
    return [i.code for i in report.issues]


# --- capture mechanics ---

def test_capture_records_refs_and_metric_values():
    with evidence.capture() as cap, _scope():
        base = evidence.query_metric_baseline("save_rate", "tiktok")
        posts = evidence.search_content_posts(["tiktok"], "save_rate")
    snap = cap.snapshot()
    assert set(base["evidence_refs"]) <= snap["refs"]
    assert set(posts["evidence_refs"]) <= snap["refs"]
    entry = snap["metrics"][base["evidence_refs"][0]]
    assert entry["lift_ratio"] == base["lift_ratio"]
    assert entry["current_value"] == base["current_value"]
    assert entry["baseline_value"] == base["baseline_value"]


def test_capture_skips_failed_tool_calls():
    with evidence.capture() as cap, evidence.scope("ws_x", "camp_other", None, None, None, None):
        r = evidence.query_metric_baseline("save_rate", "tiktok")
    assert not r["ok"]
    assert cap.snapshot()["refs"] == set()


def test_nested_capture_reuses_outer():
    with evidence.capture() as outer:
        with evidence.capture() as inner, _scope():
            assert inner is outer
            evidence.query_metric_baseline("save_rate", "tiktok")
    assert outer.snapshot()["refs"]


# --- reviewer grounding gate ---

def test_grounded_stub_payload_passes():
    payload, snap = _run_stub_pipeline()
    report = reviewer.review(payload, snap)
    assert report.passed, [i.message for i in report.issues]


def test_no_grounding_keeps_structural_behavior():
    payload, _ = _run_stub_pipeline()
    assert reviewer.review(payload).passed


def test_fabricated_signal_ref_is_ungrounded():
    payload, snap = _run_stub_pipeline()
    payload.signals[0].evidence_refs.append("metric_made_up_ref")
    report = reviewer.review(payload, snap)
    assert not report.passed
    assert ValidationIssueCode.UNGROUNDED_EVIDENCE in _codes(report)


def test_numeric_mismatch_is_ungrounded():
    payload, snap = _run_stub_pipeline()
    payload.signals[0].lift_ratio = payload.signals[0].lift_ratio * 3 + 1
    report = reviewer.review(payload, snap)
    assert not report.passed
    assert ValidationIssueCode.UNGROUNDED_EVIDENCE in _codes(report)


def test_small_rounding_passes_tolerance():
    payload, snap = _run_stub_pipeline()
    payload.signals[0].lift_ratio = round(payload.signals[0].lift_ratio * 1.01, 2)
    report = reviewer.review(payload, snap)
    assert report.passed, [i.message for i in report.issues]


def test_fabricated_hypothesis_ref_is_unknown():
    payload, snap = _run_stub_pipeline()
    payload.hypotheses[0].supporting_evidence_refs.append("note_made_up")
    report = reviewer.review(payload, snap)
    assert not report.passed
    assert ValidationIssueCode.UNKNOWN_EVIDENCE_REF in _codes(report)


def test_empty_capture_skips_grounding():
    # Tools returned nothing (capture inactive in tool context, or all calls
    # failed): the gate must not flag everything, it must skip.
    payload, _ = _run_stub_pipeline()
    report = reviewer.review(payload, {"refs": set(), "metrics": {}})
    assert report.passed


# --- backtrack routing ---

def test_ungrounded_routes_to_analyst():
    assert failure.route([ValidationIssueCode.UNGROUNDED_EVIDENCE]) == "analyst"
    # Mixed with a writer-side issue, the earliest pipeline stage wins.
    assert failure.route([
        ValidationIssueCode.MISSING_SCHEDULE,
        ValidationIssueCode.UNGROUNDED_EVIDENCE,
    ]) == "analyst"
