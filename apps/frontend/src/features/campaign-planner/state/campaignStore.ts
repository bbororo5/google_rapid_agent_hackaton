// User-created campaigns shown on the home page. Each campaign maps to its own
// planner thread. Stored in localStorage so cards survive refresh. (The demo
// "Comeback Teaser" campaign is hard-coded in the page and not stored here.)

export interface CampaignEntry {
  id: string;
  name: string;
  threadId: string | null;
  streamUrl: string | null;
  createdAt: number;
  updatedAt: number;
}

const STORAGE_KEY = "launchpilot.campaigns";

function readAll(): CampaignEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((e): e is CampaignEntry => Boolean(e) && typeof (e as CampaignEntry).id === "string" && typeof (e as CampaignEntry).name === "string");
  } catch {
    return [];
  }
}

function writeAll(entries: CampaignEntry[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // storage unavailable (private mode) -> best effort
  }
}

export function listCampaigns(): CampaignEntry[] {
  return readAll().sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getCampaign(id: string): CampaignEntry | null {
  return readAll().find((e) => e.id === id) ?? null;
}

export function addCampaign(name: string, now: number): CampaignEntry {
  const entries = readAll();
  const entry: CampaignEntry = {
    id: `camp_${now}_${Math.floor((now % 1000) + entries.length)}`,
    name: name.trim().slice(0, 80) || "New campaign",
    threadId: null,
    streamUrl: null,
    createdAt: now,
    updatedAt: now,
  };
  entries.push(entry);
  writeAll(entries);
  return entry;
}

// Bind the live thread to a campaign so re-opening the card restores it.
export function setCampaignThread(id: string, threadId: string, streamUrl: string, now: number) {
  const entries = readAll();
  const entry = entries.find((e) => e.id === id);
  if (!entry) return;
  entry.threadId = threadId;
  entry.streamUrl = streamUrl;
  entry.updatedAt = now;
  writeAll(entries);
}

export function removeCampaign(id: string) {
  writeAll(readAll().filter((e) => e.id !== id));
}
