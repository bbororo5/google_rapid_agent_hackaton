import { NextResponse } from "next/server";

interface ApprovalPayload {
  final_experiments?: Array<{ title?: string }>;
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ agentRunId: string }> }
) {
  const { agentRunId } = await params;
  
  let reqBody: ApprovalPayload = {};
  try {
    reqBody = (await request.json()) as ApprovalPayload;
  } catch {
    // ignore
  }

  const finalExperiments = reqBody.final_experiments || [];
  const firstExperiment = finalExperiments[0];
  const approvedTitle = firstExperiment?.title || "BTS face-first hook test";

  return NextResponse.json({
    "ok": true,
    "message": `Human approval processed successfully for run ${agentRunId}.`,
    "growth_brief_id": "brief_20260601_001",
    "created_calendar_events": [
      {
        "event_id": "cal_101",
        "title": approvedTitle,
        "scheduled_at": "2026-06-03T20:00:00+09:00"
      }
    ],
    "persisted_at": "2026-06-01T16:33:15+09:00"
  });
}
