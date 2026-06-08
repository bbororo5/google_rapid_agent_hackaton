"""결함A: evidence queries scoped to campaign/workspace + time-window baseline.

Runs in STUB mode (conftest blanks real ES/MCP), so these exercise the seed
backend + the shared compute_baseline + the pure filter builders.
"""
from app.tools import es_client, evidence, mcp_client, seed

DEMO_WS = seed.WORKSPACE_ID
DEMO_CAMP = seed.CAMPAIGN_ID


def _scope(ws=DEMO_WS, camp=DEMO_CAMP):
    return evidence.scope(ws, camp, None, None, None, None)


# --- tenancy isolation (the core defect) ---

def test_demo_campaign_sees_its_evidence():
    with _scope():
        r = evidence.query_metric_baseline("save_rate", "tiktok")
    assert r["ok"] and r["lift_ratio"] > 0


def test_other_campaign_baseline_is_empty():
    with _scope(camp="camp_other"):
        r = evidence.query_metric_baseline("save_rate", "tiktok")
    assert not r["ok"]
    assert r["error"]["code"] == "NO_EVIDENCE_FOUND"


def test_other_campaign_content_search_is_empty():
    with _scope(camp="camp_other"):
        r = evidence.search_content_posts(["tiktok"], "save_rate")
    assert not r["ok"]


def test_other_campaign_team_notes_empty():
    with _scope():
        ok = evidence.search_team_notes("BTS")
    assert ok["ok"] and ok["evidence_refs"]
    with _scope(camp="camp_other"):
        miss = evidence.search_team_notes("BTS")
    assert not miss["ok"]


def test_no_scope_is_unfiltered():
    # A context-less turn (no scope bound) must still see the seed data.
    r = evidence.query_metric_baseline("save_rate", "tiktok")
    assert r["ok"]


# --- time-window baseline (Option B) ---

def _posts(metric, channel, pairs):
    return [
        {"post_id": pid, "channel": channel, "published_at": day, "metrics": {metric: val}}
        for pid, day, val in pairs
    ]


def test_compute_baseline_uses_explicit_windows():
    posts = _posts("m", "tiktok", [
        ("a", "2026-05-01", 1.0), ("b", "2026-05-02", 1.0),
        ("c", "2026-06-05", 3.0), ("d", "2026-06-06", 3.0),
    ])
    r = es_client.compute_baseline(
        posts, "m", "tiktok",
        current_start="2026-06-02", current_end="2026-06-08",
        baseline_start="2026-04-25", baseline_end="2026-06-01",
    )
    assert r["ok"]
    assert r["current_value"] == 3.0
    assert r["baseline_value"] == 1.0
    assert r["lift_ratio"] == 3.0


def test_compute_baseline_sparse_window_falls_back_to_recency():
    # current window has no posts -> fall back to recency split over all rows.
    posts = _posts("m", "tiktok", [
        ("a", "2026-05-01", 1.0), ("b", "2026-05-02", 1.0),
        ("c", "2026-05-03", 3.0), ("d", "2026-05-04", 3.0),
    ])
    r = es_client.compute_baseline(
        posts, "m", "tiktok",
        current_start="2026-06-02", current_end="2026-06-08",
        baseline_start="2026-04-25", baseline_end="2026-06-01",
    )
    assert r["ok"]
    assert r["current_value"] == 3.0   # latest half
    assert r["baseline_value"] == 1.0  # earlier half


def test_compute_baseline_handles_datetime_published_at():
    posts = _posts("m", "tiktok", [
        ("a", "2026-05-01T10:00:00+09:00", 1.0), ("b", "2026-05-02T10:00:00+09:00", 1.0),
        ("c", "2026-06-08T20:00:00+09:00", 4.0), ("d", "2026-06-07T20:00:00+09:00", 4.0),
    ])
    r = es_client.compute_baseline(
        posts, "m", "tiktok",
        current_start="2026-06-02", current_end="2026-06-08",
        baseline_start="2026-04-25", baseline_end="2026-06-01",
    )
    assert r["ok"]
    assert r["current_value"] == 4.0  # boundary 2026-06-08 included via day-normalization
    assert r["baseline_value"] == 1.0


# --- pure filter builders ---

def test_es_tenancy_filters_drop_none():
    assert es_client._tenancy_filters(None, None, None) == []
    f = es_client._tenancy_filters("ws", "camp", "2026-05-01")
    assert {"term": {"workspace_id": "ws"}} in f
    assert {"term": {"campaign_id": "camp"}} in f
    assert {"range": {"published_at": {"gte": "2026-05-01"}}} in f


def test_mcp_tenancy_clauses_param_order():
    clauses, params = mcp_client._tenancy_clauses("ws", "camp", "2026-05-01")
    assert clauses == ["campaign_id == ?", "workspace_id == ?", "published_at >= ?"]
    assert params == ["camp", "ws", "2026-05-01"]
    assert mcp_client._tenancy_clauses(None, None, None) == ([], [])
