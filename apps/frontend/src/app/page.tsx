"use client";

import Link from "next/link";
import { ArrowRight, CalendarDays, FileText, FolderOpen, FlaskConical, Target } from "lucide-react";

export default function CampaignsHome() {
  return (
    <main className="campaigns-home">
      <header className="campaigns-header">
        <div>
          <div className="campaign-kicker">LaunchPilot MVP</div>
          <h1>Campaigns</h1>
          <p>Choose a campaign to review evidence, plan next-week experiments, and approve outputs.</p>
        </div>
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
            <Link className="primary-link" href="/campaigns/comeback-teaser/planner">
              <FlaskConical size={18} strokeWidth={1.8} />
              Open Experiment Planner
              <ArrowRight size={18} strokeWidth={1.8} />
            </Link>
          </div>
        </article>
      </section>
    </main>
  );
}
