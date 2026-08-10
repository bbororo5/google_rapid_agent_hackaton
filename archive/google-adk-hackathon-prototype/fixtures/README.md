# Test fixtures

## `comeback-campaign-metrics.csv`

46 rows of SNS post performance across **4 channels** over **4 weeks**
(2026-05-04 → 2026-05-31), shaped so you can exercise different agent behaviors.

CSV columns: `post_id, published_at, channel, title, permalink` (descriptive) +
numeric metric columns (`views, likes, comments, shares, saves, save_rate,
engagement_rate, follower_count, watch_time_sec, retention_rate`). The Java
importer treats every non-descriptive column as a metric (contract 03).
`workspace_id` / `campaign_id` are upload params, not CSV columns.

### Embedded patterns (what to test)

| Channel | Pattern | Expected agent behavior |
|---|---|---|
| **tiktok** | `save_rate` ~0.024 weeks 1-3 → **0.074-0.083** in the comeback week (≈3x) | **Strong signal** (lift ≥ 2.0). Analyst flags it, strategist ties it to the BTS teaser, writer proposes a repeat. |
| **youtube** | steady climb 0.015 → 0.022 (~1.4x) | **Weak signal** (1.3-2.0 band) — borderline, good for testing the threshold. |
| **instagram** | flat ~0.023-0.025 | **Noise** (below 1.3) — should be dropped. |
| **x** | engagement/views **declining** | Negative trend — no positive signal; tests that the analyst doesn't fabricate one. |

Other things to test: multiple metrics per post, a follower_count that grows
over time, video-only metrics (`watch_time_sec`, `retention_rate`) being 0 on
photo/text posts, and `gemini-flash-latest` summarizing the spike into an
experiment plan.

### Upload (local)

```bash
# via Java backend import endpoint (contract 01)
curl -F "file=@fixtures/comeback-campaign-metrics.csv" \
     "http://localhost:8080/api/import/csv?workspace_id=demo_workspace&campaign_id=camp_comeback_teaser"
```

(Or upload it through the frontend CSV button once that screen is wired.)

> Note: the Python agent currently reads evidence from seeded stub data until
> the Elastic MCP path is implemented, so importing this CSV exercises the
> Java→Elastic write path. Once Elastic MCP is wired, these rows drive the
> analyst's real signal detection.
