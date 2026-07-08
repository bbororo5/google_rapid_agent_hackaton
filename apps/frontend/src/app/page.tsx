"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarDays, FileText, FolderOpen, FlaskConical, MessageSquare, Plus, Target, Trash2 } from "lucide-react";
import { addCampaign, listCampaigns, removeCampaign, type CampaignEntry } from "@/features/campaign-planner/state/campaignStore";

const PLANNER_PATH = "/campaigns/comeback-teaser/planner";

function formatWhen(ts: number) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return "";
  }
}

export default function CampaignsHome() {
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<CampaignEntry[]>([]);

  useEffect(() => {
    setCampaigns(listCampaigns());
  }, []);

  function handleAdd() {
    const name = window.prompt("새 캠페인 이름", "새 캠페인");
    if (name === null) return; // cancelled
    const entry = addCampaign(name, Date.now());
    router.push(`${PLANNER_PATH}?campaign=${encodeURIComponent(entry.id)}`);
  }

  function handleDelete(id: string) {
    removeCampaign(id);
    setCampaigns(listCampaigns());
  }

  return (
    <main className="campaigns-home">
      <header className="campaigns-header">
        <div>
          <div className="campaign-kicker">LaunchPilot MVP</div>
          <h1>캠페인</h1>
          <p>캠페인을 선택해 근거를 검토하고, 다음 주 실험을 기획하고, 산출물을 승인하세요.</p>
        </div>
        <button type="button" className="new-conversation-button" onClick={handleAdd}>
          <Plus size={16} strokeWidth={2} />
          캠페인 추가
        </button>
      </header>

      <section className="campaign-list" aria-label="캠페인 목록">
        <article className="campaign-entry">
          <div className="campaign-entry-main">
            <div className="campaign-entry-icon">
              <FolderOpen size={22} strokeWidth={1.8} />
            </div>
            <div>
              <span className="demo-label">데모 캠페인</span>
              <h2>컴백 티저 캠페인</h2>
              <p>SNS 지표, 팀 노트, 캘린더 이벤트, 이전 브리프가 포함된 K-pop 크리에이터 론칭 데이터셋.</p>
            </div>
          </div>

          <div className="campaign-entry-meta" aria-label="캠페인 데이터 요약">
            <span>
              <Target size={15} strokeWidth={1.8} />
              진행 중
            </span>
            <span>
              <CalendarDays size={15} strokeWidth={1.8} />
              2026-05-25 ~ 2026-06-01
            </span>
            <span>
              <FileText size={15} strokeWidth={1.8} />
              시드 데이터셋
            </span>
          </div>

          <div className="campaign-entry-action">
            <Link className="primary-link" href={PLANNER_PATH}>
              <FlaskConical size={18} strokeWidth={1.8} />
              Open Experiment Planner
              <ArrowRight size={18} strokeWidth={1.8} />
            </Link>
          </div>
        </article>

        {campaigns.map((campaign) => (
          <article className="campaign-entry" key={campaign.id}>
            <div className="campaign-entry-main">
              <div className="campaign-entry-icon">
                <MessageSquare size={22} strokeWidth={1.8} />
              </div>
              <div>
                <span className="demo-label">캠페인</span>
                <h2>{campaign.name}</h2>
                <p>{campaign.threadId ? "분석 세션이 진행 중이에요. 열어서 이어가세요." : "새 캠페인이에요. 플래너를 열고 베이스라인 분석을 요청하거나 CSV를 첨부하세요."}</p>
              </div>
            </div>

            <div className="campaign-entry-meta" aria-label="캠페인 데이터 요약">
              <span>
                <CalendarDays size={15} strokeWidth={1.8} />
                생성일 {formatWhen(campaign.createdAt)}
              </span>
            </div>

            <div className="campaign-entry-action campaign-entry-action-row">
              <Link className="primary-link" href={`${PLANNER_PATH}?campaign=${encodeURIComponent(campaign.id)}`}>
                <FlaskConical size={18} strokeWidth={1.8} />
                실험 플래너 열기
                <ArrowRight size={18} strokeWidth={1.8} />
              </Link>
              <button
                type="button"
                className="campaign-delete-button"
                aria-label="캠페인 삭제"
                title="캠페인 삭제"
                onClick={() => handleDelete(campaign.id)}
              >
                <Trash2 size={16} strokeWidth={1.8} />
              </button>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
