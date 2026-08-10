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
    const name = window.prompt("New campaign name", "New Campaign");
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
          <h1>Campaigns</h1>
          <p>Choose a campaign to review evidence, plan next-week experiments, and approve outputs.</p>
        </div>
        <button type="button" className="new-conversation-button" onClick={handleAdd}>
          <Plus size={16} strokeWidth={2} />
          Add campaign
        </button>
      </header>

      <section className="campaign-list" aria-label="Campaign list">
        <article className="campaign-entry">
          <div className="campaign-entry-main">
            <div className="campaign-entry-icon">
              <FolderOpen size={22} strokeWidth={1.8} />
            </div>
            <div>
              <span className="demo-label">Demo campaign</span>
              <h2>Comeback Teaser Campaign</h2>
              <p>K-pop creator launch dataset with SNS metrics, team notes, calendar events, and prior briefs.</p>
            </div>
          </div>

          <div className="campaign-entry-meta" aria-label="Campaign data summary">
            <span>
              <Target size={15} strokeWidth={1.8} />
              Active
            </span>
            <span>
              <CalendarDays size={15} strokeWidth={1.8} />
              2026-05-25 to 2026-06-01
            </span>
            <span>
              <FileText size={15} strokeWidth={1.8} />
              Seed dataset
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
                <span className="demo-label">Campaign</span>
                <h2>{campaign.name}</h2>
                <p>{campaign.threadId ? "Analysis session in progress. Open to continue." : "New campaign. Open the planner and ask to analyze the baseline or attach a CSV."}</p>
              </div>
            </div>

            <div className="campaign-entry-meta" aria-label="Campaign data summary">
              <span>
                <CalendarDays size={15} strokeWidth={1.8} />
                Created {formatWhen(campaign.createdAt)}
              </span>
            </div>

            <div className="campaign-entry-action campaign-entry-action-row">
              <Link className="primary-link" href={`${PLANNER_PATH}?campaign=${encodeURIComponent(campaign.id)}`}>
                <FlaskConical size={18} strokeWidth={1.8} />
                Open Experiment Planner
                <ArrowRight size={18} strokeWidth={1.8} />
              </Link>
              <button
                type="button"
                className="campaign-delete-button"
                aria-label="Delete campaign"
                title="Delete campaign"
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
