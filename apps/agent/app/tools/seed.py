"""Seeded demo evidence for STUB mode (no live Elastic).

Mirrors the BTS comeback example used across the docs: save_rate jumps from a
~2.6% baseline to ~7.4% (a 2.8x lift) on the back of a teaser clip. The numbers
match contracts/04 example responses so stub output is contract-faithful.

In real mode (ELASTIC_MCP_URL set) the wrapper would query the Elastic MCP
server instead; see app/tools/mcp_client.py.
"""
from __future__ import annotations

# content_posts rows (subset of fields relevant to the demo).
CONTENT_POSTS: list[dict] = [
    {
        "post_id": "post_bts_teaser_01",
        "channel": "tiktok",
        "published_at": "2026-05-28",
        "title": "BTS comeback teaser - 30s clip",
        "metrics": {"views": 412000, "saves": 30500, "save_rate": 0.074, "shares": 9100},
    },
    {
        "post_id": "post_bts_teaser_02",
        "channel": "youtube",
        "published_at": "2026-05-29",
        "title": "Behind the teaser",
        "metrics": {"views": 188000, "saves": 12100, "save_rate": 0.064, "shares": 4200},
    },
    {
        "post_id": "post_routine_03",
        "channel": "tiktok",
        "published_at": "2026-05-12",
        "title": "Weekly routine clip",
        "metrics": {"views": 96000, "saves": 2500, "save_rate": 0.026, "shares": 800},
    },
]

# Pre-computed metric baselines (current vs prior window) by metric+channel.
METRIC_BASELINES: dict[tuple[str, str], dict] = {
    ("save_rate", "tiktok"): {"current_value": 0.074, "baseline_value": 0.026},
    ("save_rate", "youtube"): {"current_value": 0.064, "baseline_value": 0.028},
    ("shares", "tiktok"): {"current_value": 9100.0, "baseline_value": 800.0},
}

# team_notes (qualitative). Empty list => strategist tool returns NO_EVIDENCE.
TEAM_NOTES: list[dict] = [
    {
        "note_id": "note_bts_comeback",
        "text": "Dropped the BTS comeback teaser clip last week; fan accounts reposted heavily.",
        "created_at": "2026-05-27",
        "channel": "tiktok",
    },
]
