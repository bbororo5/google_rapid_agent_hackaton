import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json(
    {
      "ok": true,
      "import_id": "imp_20260601_001",
      "workspace_id": "demo_workspace",
      "campaign_id": "camp_comeback_teaser",
      "indexed_count": 184,
      "failed_count": 0,
      "columns": [
        "post_id",
        "published_at",
        "channel",
        "views",
        "likes",
        "comments",
        "save_rate"
      ],
      "created_at": "2026-06-01T16:30:10+09:00"
    },
    { status: 201 }
  );
}
