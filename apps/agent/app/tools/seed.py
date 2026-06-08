"""Seeded demo evidence for STUB mode (no live Elastic).

Mirrors the BTS comeback example used across the docs: save_rate jumps from a
~2.6% baseline to ~7.4% (a 2.8x lift) on the back of a teaser clip. The numbers
match contracts/04 example responses so stub output is contract-faithful.

This is intentionally a broad baseline: many channels x metrics, several with a
>=2.0x lift, so the analyst surfaces multiple strong signals (and the pipeline
drafts multiple experiments) instead of a single one.

In real mode (ELASTIC_MCP_URL set) the wrapper would query the Elastic MCP
server instead; see app/tools/mcp_client.py.
"""
from __future__ import annotations

# The seeded demo is single-tenant; these match contracts/03 examples and the
# golden-path tests. Stamped onto every row below so the tenancy filter (which
# real ES/MCP applies server-side) behaves identically in STUB mode.
WORKSPACE_ID = "demo_workspace"
CAMPAIGN_ID = "camp_comeback_teaser"

# content_posts rows (subset of fields relevant to the demo).
CONTENT_POSTS: list[dict] = [
    {
        "post_id": "post_bts_teaser_01",
        "channel": "tiktok",
        "published_at": "2026-05-28",
        "title": "BTS comeback teaser - 30s clip",
        "metrics": {"views": 412000, "saves": 30500, "save_rate": 0.074, "shares": 9100, "comments": 5200},
    },
    {
        "post_id": "post_bts_teaser_02",
        "channel": "youtube",
        "published_at": "2026-05-29",
        "title": "Behind the teaser",
        "metrics": {"views": 188000, "saves": 12100, "save_rate": 0.064, "shares": 4200, "watch_time": 0.58},
    },
    {
        "post_id": "post_bts_teaser_03",
        "channel": "instagram",
        "published_at": "2026-05-30",
        "title": "Teaser still carousel",
        "metrics": {"views": 240000, "saves": 18800, "save_rate": 0.078, "shares": 6100, "comments": 3900},
    },
    {
        "post_id": "post_bts_reel_04",
        "channel": "instagram",
        "published_at": "2026-05-31",
        "title": "Choreo snippet reel",
        "metrics": {"views": 305000, "saves": 21300, "save_rate": 0.070, "shares": 7400, "comments": 4500},
    },
    {
        "post_id": "post_bts_short_05",
        "channel": "youtube",
        "published_at": "2026-06-01",
        "title": "Comeback countdown short",
        "metrics": {"views": 156000, "saves": 9300, "save_rate": 0.060, "shares": 3100, "watch_time": 0.62},
    },
    {
        "post_id": "post_bts_thread_06",
        "channel": "x",
        "published_at": "2026-06-01",
        "title": "Comeback teaser drop thread",
        "metrics": {"views": 520000, "saves": 4100, "save_rate": 0.008, "shares": 14200, "comments": 8800},
    },
    {
        "post_id": "post_fanart_07",
        "channel": "x",
        "published_at": "2026-06-02",
        "title": "Fan art repost",
        "metrics": {"views": 210000, "saves": 1800, "save_rate": 0.009, "shares": 9600, "comments": 5100},
    },
    {
        "post_id": "post_clip_remix_08",
        "channel": "tiktok",
        "published_at": "2026-06-02",
        "title": "Teaser remix duet",
        "metrics": {"views": 388000, "saves": 26900, "save_rate": 0.069, "shares": 11200, "comments": 6300},
    },
    # --- prior-window baselines (typical, pre-comeback posts) ---
    {
        "post_id": "post_routine_09",
        "channel": "tiktok",
        "published_at": "2026-05-12",
        "title": "Weekly routine clip",
        "metrics": {"views": 96000, "saves": 2500, "save_rate": 0.026, "shares": 800, "comments": 900},
    },
    {
        "post_id": "post_routine_10",
        "channel": "youtube",
        "published_at": "2026-05-10",
        "title": "Studio vlog",
        "metrics": {"views": 84000, "saves": 2350, "save_rate": 0.028, "shares": 740, "watch_time": 0.41},
    },
    {
        "post_id": "post_routine_11",
        "channel": "instagram",
        "published_at": "2026-05-11",
        "title": "Daily story recap",
        "metrics": {"views": 70000, "saves": 2100, "save_rate": 0.030, "shares": 690, "comments": 760},
    },
    {
        "post_id": "post_routine_12",
        "channel": "x",
        "published_at": "2026-05-09",
        "title": "Schedule announcement",
        "metrics": {"views": 130000, "saves": 950, "save_rate": 0.007, "shares": 2300, "comments": 1400},
    },
]

# Pre-computed metric baselines (current vs prior window) by metric+channel.
# lift_ratio = current / baseline. >=2.0 reads as a STRONG signal (analyst rule).
METRIC_BASELINES: dict[tuple[str, str], dict] = {
    # save_rate spikes across the visual channels (strong)
    ("save_rate", "tiktok"): {"current_value": 0.074, "baseline_value": 0.026},
    ("save_rate", "youtube"): {"current_value": 0.064, "baseline_value": 0.028},
    ("save_rate", "instagram"): {"current_value": 0.078, "baseline_value": 0.030},
    # shares blow up on the conversational channels (strong)
    ("shares", "tiktok"): {"current_value": 11200.0, "baseline_value": 800.0},
    ("shares", "x"): {"current_value": 14200.0, "baseline_value": 2300.0},
    ("shares", "instagram"): {"current_value": 7400.0, "baseline_value": 690.0},
    # comments engagement up (strong on x, moderate elsewhere)
    ("comments", "x"): {"current_value": 8800.0, "baseline_value": 1400.0},
    ("comments", "tiktok"): {"current_value": 6300.0, "baseline_value": 900.0},
    # views lift (moderate-to-strong)
    ("views", "tiktok"): {"current_value": 412000.0, "baseline_value": 96000.0},
    ("views", "x"): {"current_value": 520000.0, "baseline_value": 130000.0},
    ("views", "youtube"): {"current_value": 188000.0, "baseline_value": 84000.0},
    # youtube watch-time retention (moderate)
    ("watch_time", "youtube"): {"current_value": 0.62, "baseline_value": 0.41},
}

# Stamp tenancy onto every content_posts row (matches the real ES doc schema).
for _p in CONTENT_POSTS:
    _p["workspace_id"] = WORKSPACE_ID
    _p["campaign_id"] = CAMPAIGN_ID


# team_notes (qualitative). Empty list => strategist tool returns NO_EVIDENCE.
TEAM_NOTES: list[dict] = [
    {
        "note_id": "note_bts_comeback",
        "text": "Dropped the BTS comeback teaser clip last week; fan accounts reposted heavily.",
        "created_at": "2026-05-27",
        "channel": "tiktok",
    },
    {
        "note_id": "note_ig_carousel",
        "text": "Instagram teaser-still carousel outperformed reels for saves; fans screenshotting frames.",
        "created_at": "2026-05-30",
        "channel": "instagram",
    },
    {
        "note_id": "note_x_thread",
        "text": "X drop thread got mass quote-reposts from fan translation accounts within an hour.",
        "created_at": "2026-06-01",
        "channel": "x",
    },
    {
        "note_id": "note_yt_short",
        "text": "YouTube countdown shorts held watch-time well; viewers re-watching the choreo beat.",
        "created_at": "2026-06-01",
        "channel": "youtube",
    },
    {
        "note_id": "note_remix_duet",
        "text": "Teaser remix duets on TikTok drove a second shares wave; UGC trend forming.",
        "created_at": "2026-06-02",
        "channel": "tiktok",
    },
]

# Stamp tenancy onto every team_notes row.
for _n in TEAM_NOTES:
    _n["workspace_id"] = WORKSPACE_ID
    _n["campaign_id"] = CAMPAIGN_ID
