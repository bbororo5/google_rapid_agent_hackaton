package com.launchpilot.mock;

import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;

final class MockPayloads {
    static final String RUN_ID = "run_20260601_001";
    static final String SESSION_ID = "session_20260601_001";

    private MockPayloads() {
    }

    static Map<String, Object> importCsv() {
        return Map.of(
                "ok", true,
                "import_id", "imp_20260601_001",
                "workspace_id", "demo_workspace",
                "campaign_id", "camp_comeback_teaser",
                "indexed_count", 184,
                "failed_count", 0,
                "columns", List.of("post_id", "published_at", "channel", "views", "likes", "comments", "save_rate"),
                "created_at", "2026-06-01T16:30:10+09:00"
        );
    }

    static Map<String, Object> acceptedRun(String publicBaseUrl) {
        return Map.of(
                "ok", true,
                "agent_run_id", RUN_ID,
                "status", "PENDING",
                "stream_url", publicBaseUrl.replace("http://", "ws://").replace("https://", "wss://") + "/api/agent/runs/" + RUN_ID + "/stream",
                "next_poll_url", publicBaseUrl + "/api/agent/runs/" + RUN_ID,
                "created_at", "2026-06-01T16:31:00+09:00"
        );
    }

    static Map<String, Object> readyRun(String agentRunId) {
        return map(
                "agent_run_id", agentRunId,
                "status", "WAITING_FOR_APPROVAL",
                "current_stage", "WAIT_FOR_APPROVAL",
                "retry_count", 0,
                "error_message", null,
                "payload", payload(),
                "tool_call_logs", List.of(
                        Map.of("sequence", 1, "tool_name", "query_metric_baseline", "status", "SUCCESS", "duration_ms", 142),
                        Map.of("sequence", 2, "tool_name", "search_team_notes", "status", "SUCCESS", "duration_ms", 310)
                )
        );
    }

    static Map<String, Object> approvalResponse(String title) {
        return Map.of(
                "ok", true,
                "message", "Human approval processed successfully.",
                "growth_brief_id", "brief_20260601_001",
                "created_calendar_events", List.of(Map.of(
                        "event_id", "cal_20260603_001",
                        "title", title,
                        "scheduled_at", "2026-06-03T20:00:00+09:00"
                )),
                "persisted_at", "2026-06-01T16:33:15+09:00"
        );
    }

    static Map<String, Object> payload() {
        return map(
                "signals", List.of(map(
                        "id", "sig_001",
                        "type", "content_outperformance",
                        "title", "BTS shorts outperformed recent baseline",
                        "description", "Two behind-the-scenes TikTok shorts showed save rates 2.8x above the 30-day channel baseline.",
                        "metric_name", "save_rate",
                        "current_value", 0.074,
                        "baseline_value", 0.026,
                        "lift_ratio", 2.8,
                        "date_window", Map.of("start", "2026-05-25", "end", "2026-06-01"),
                        "confidence", "high",
                        "evidence_refs", List.of("post_014", "post_017", "note_006")
                )),
                "hypotheses", List.of(map(
                        "id", "hyp_001",
                        "signal_ids", List.of("sig_001"),
                        "statement", "Raw behind-the-scenes clips may be converting passive viewers into deeper engagement better than polished teaser assets.",
                        "rationale", "The strongest posts share the BTS angle and face-first hook, and team notes mention strong fan reaction to raw practice footage.",
                        "confidence", "medium_high",
                        "supporting_evidence_refs", List.of("post_014", "post_017", "note_006"),
                        "caveats", List.of("External fan community activity was not measured.", "This is a correlation, not a causal claim.")
                )),
                "experiment_plan", map(
                        "id", "plan_001",
                        "summary", "This week's strongest signal is repeated overperformance from BTS short-form clips.",
                        "overall_confidence", "medium_high",
                        "items", List.of(map(
                                "id", "exp_001",
                                "hypothesis_id", "hyp_001",
                                "title", "BTS face-first hook test",
                                "channel", "tiktok",
                                "content_format", "12-second short",
                                "hook", "Open with a close-up reaction in the first 2 seconds.",
                                "cta", "Ask fans to comment which practice moment they want next.",
                                "target_metric", "save_rate",
                                "success_criteria", "save_rate >= 1.5x TikTok 30-day baseline within 48 hours",
                                "scheduled_at", "2026-06-03T20:00:00+09:00",
                                "production_brief", "Use raw rehearsal footage, minimal polish, subtitles on-screen."
                        ))
                )
        );
    }

    private static Map<String, Object> map(Object... entries) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int index = 0; index < entries.length; index += 2) {
            result.put((String) entries[index], entries[index + 1]);
        }
        return result;
    }
}
