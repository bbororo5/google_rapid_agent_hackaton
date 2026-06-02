import { NextResponse } from "next/server";

interface CancelPayload {
  reason?: string;
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ agentRunId: string }> }
) {
  const { agentRunId } = await params;

  try {
    (await request.json()) as CancelPayload;
  } catch {
    // ignore
  }

  return NextResponse.json(
    {
      ok: true,
      agent_run_id: agentRunId,
      status: "CANCELLED",
      cancelled_at: new Date().toISOString(),
    },
    { status: 202 }
  );
}
