import { NextResponse } from "next/server";

// Keep a simple polling count in memory for mock flow
let pollCount = 0;

export async function GET(
  request: Request,
  { params }: { params: Promise<{ agentRunId: string }> }
) {
  const { agentRunId } = await params;

  // Whenever a new run starts or is reset, pollCount could be reset.
  // For simplicity, we increment it each time.
  pollCount += 1;

  if (pollCount === 1) {
    return NextResponse.json({
      "agent_run_id": agentRunId,
      "status": "RUNNING_EVIDENCE_SEARCH",
      "current_stage": "SEARCHING_EVIDENCE",
      "retry_count": 0,
      "error_message": null,
      "payload": null,
      "tool_call_logs": [
        {
          "sequence": 1,
          "tool_name": "query_metric_baseline",
          "status": "SUCCESS",
          "duration_ms": 142
        }
      ]
    });
  }

  // Reset after ready so next analysis restarts fresh
  pollCount = 0;

  return NextResponse.json({
    "agent_run_id": agentRunId,
    "status": "WAITING_FOR_APPROVAL",
    "current_stage": "VALIDATING",
    "retry_count": 0,
    "error_message": null,
    "payload": {
      "signals": [
        {
          "id": "sig_001",
          "type": "content_outperformance",
          "title": "BTS shorts outperformed recent baseline",
          "description": "Two behind-the-scenes TikTok shorts showed save rates 2.8x above the 30-day channel baseline.",
          "metric_name": "save_rate",
          "current_value": 0.074,
          "baseline_value": 0.026,
          "lift_ratio": 2.8,
          "date_window": {
            "start": "2026-05-25",
            "end": "2026-06-01"
          },
          "confidence": "high",
          "evidence_refs": [
            "post_014",
            "post_017",
            "note_006"
          ]
        }
      ],
      "hypotheses": [
        {
          "id": "hyp_001",
          "signal_ids": [
            "sig_001"
          ],
          "statement": "Raw behind-the-scenes clips may be converting passive viewers into deeper engagement better than polished teaser assets.",
          "rationale": "The strongest posts share the BTS angle and face-first hook, and team notes mention strong fan reaction to raw practice footage.",
          "confidence": "medium_high",
          "supporting_evidence_refs": [
            "post_014",
            "post_017",
            "note_006"
          ],
          "caveats": [
            "External fan community activity was not measured.",
            "This is a correlation, not a causal claim."
          ]
        }
      ],
      "experiment_plan": {
        "id": "plan_001",
        "summary": "This week's strongest signal is repeated overperformance from BTS short-form clips. Next week should test whether the same raw format can reproduce engagement uplift across TikTok and Instagram.",
        "overall_confidence": "medium_high",
        "items": [
          {
            "id": "exp_001",
            "hypothesis_id": "hyp_001",
            "title": "BTS face-first hook test",
            "channel": "tiktok",
            "content_format": "12-second short",
            "hook": "Open with a close-up reaction in the first 2 seconds.",
            "cta": "Ask fans to comment which practice moment they want next.",
            "target_metric": "save_rate",
            "success_criteria": "save_rate >= 1.5x TikTok 30-day baseline within 48 hours",
            "scheduled_at": "2026-06-03T20:00:00+09:00",
            "production_brief": "Use raw rehearsal footage, minimal polish, subtitles on-screen."
          }
        ]
      }
    },
    "tool_call_logs": [
      {
        "sequence": 1,
        "tool_name": "query_metric_baseline",
        "status": "SUCCESS",
        "duration_ms": 142
      },
      {
        "sequence": 2,
        "tool_name": "search_team_notes",
        "status": "SUCCESS",
        "duration_ms": 310
      }
    ]
  });
}
