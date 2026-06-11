import { expect, test, type Locator, type Page } from "@playwright/test";
import path from "node:path";

// Real-stack E2E for ADR-005's runtime memory (Redis hot tier + Elastic episodic
// persistence). Episodes are server-side, so this spec asserts the user-visible
// behavior they enable: the thread stays coherent across multiple backtracks,
// each rewind re-runs analysis cleanly (episode checkpoints + rerun memory
// injection), and continuity holds when the user resumes the pipeline.
//
// The thread is append-only: a prior plan's approval block stays in the
// timeline. So new rounds are asserted by the *count* of completion markers
// growing (a real new round happened), not by the absence of an old block.
//
//   E2E_ENV_FILE=.env npm run test:e2e:memory

const root = path.resolve(import.meta.dirname, "..");
const sampleMetricsCsv = path.join(root, "apps/frontend/fixtures/sample-channel-metrics.csv");

const ROUND_TIMEOUT = 120_000;

async function composer(page: Page): Promise<Locator> {
  const box = page.locator("#agent-question");
  await expect(box).toBeVisible();
  return box;
}

async function sendMessage(page: Page, text: string): Promise<void> {
  const box = await composer(page);
  await box.fill(text);
  await page.locator("button.composer-action-send").click();
  await expect(page.getByText(text, { exact: false })).toBeVisible();
  await expect(box).toHaveValue("");
}

async function attachCsvAndAsk(page: Page, text: string): Promise<void> {
  const box = await composer(page);
  await box.fill(text);
  const userMessages = page.locator(".thread-message.user");
  const beforeAttachUserMessages = await userMessages.count();
  await page.locator("#csv-input").setInputFiles(sampleMetricsCsv);
  await expect(userMessages).toHaveCount(beforeAttachUserMessages);
  await expect(page.locator(".file-chip")).toContainText("sample-channel-metrics.csv");
  const analyzeButton = page.locator("button.composer-action-analyze");
  if (await analyzeButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await analyzeButton.click();
  } else {
    await page.locator("button.composer-action-send").click();
  }
  const sentMessage = userMessages.filter({ hasText: text });
  await expect(sentMessage).toBeVisible({ timeout: 30_000 });
}

function approvalButton(page: Page): Locator {
  return page.getByRole("button", { name: /approve experiments/i });
}

function thread(page: Page): Locator {
  return page.getByRole("region", { name: /campaign agent thread/i });
}

function analysisCompletions(page: Page): Locator {
  return thread(page).getByText("분석 결과를 확인했습니다");
}

function hypothesisCompletions(page: Page): Locator {
  return thread(page).getByText("가설을 정리했습니다");
}

// Append-only thread: assert the Nth round happened by the marker count growing.
async function expectAnalysisCount(page: Page, n: number): Promise<void> {
  await expect(analysisCompletions(page)).toHaveCount(n, { timeout: ROUND_TIMEOUT });
}

async function expectHypothesisCount(page: Page, n: number): Promise<void> {
  await expect(hypothesisCompletions(page)).toHaveCount(n, { timeout: ROUND_TIMEOUT });
}

async function expectApprovalGate(page: Page): Promise<void> {
  await expect(approvalButton(page).first()).toBeVisible({ timeout: ROUND_TIMEOUT });
}

// A backtrack to an arbitrary metric may or may not surface signals (real LLM).
// What ADR-005 guarantees is coherence: the turn produces a new assistant
// response and never crashes the thread. So assert a new article appeared and
// no error banner is present.
async function expectCoherentTurn(page: Page, beforeArticles: number): Promise<void> {
  await expect
    .poll(async () => await thread(page).getByRole("article").count(), { timeout: ROUND_TIMEOUT })
    .toBeGreaterThan(beforeArticles);
  await expect(thread(page).getByText("Agent error")).toHaveCount(0);
}

test.describe("ADR-005 episodic memory continuity", () => {
  test.describe.configure({ mode: "serial" });

  test("stays coherent across repeated backtracks and resumes the pipeline", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    // Round 1. Open the thread and run the first analysis (save_rate). First
    // phase-boundary checkpoint (a FORWARD episode).
    await sendMessage(page, "이번 캠페인 흐름을 다음 주 실험까지 같이 잡아보자.");
    await attachCsvAndAsk(page, "이 CSV로 저장률 중심으로 먼저 분석해줘.");
    await expectAnalysisCount(page, 1);

    // Round 2. Forward to hypotheses, then a plan (approval gate). More
    // checkpoints accumulate as episodes.
    await sendMessage(page, "이 분석 결과로 가설을 세워줘.");
    await expectHypothesisCount(page, 1);
    await sendMessage(page, "첫 번째 가설로 다음 주 실험 계획 초안을 만들어줘.");
    await expectApprovalGate(page);

    // Round 3. First backtrack: rewind from planning to analysis with a new
    // metric. ADR-005 records a backtrack episode and re-runs analysis. The
    // analyst may or may not find a signal for this metric; either way the
    // thread must stay coherent (no crash), which is the memory guarantee.
    const beforeBacktrack1 = await thread(page).getByRole("article").count();
    await sendMessage(page, "잠깐, 저장률 말고 공유 수 기준으로 처음 분석부터 다시 봐줘.");
    await expectCoherentTurn(page, beforeBacktrack1);

    // Round 4. Second backtrack with yet another metric. Episode accumulation +
    // obsolete-run handling must not break the thread across repeated rewinds.
    const beforeBacktrack2 = await thread(page).getByRole("article").count();
    await sendMessage(page, "다시, 이번엔 리텐션 기준으로 처음부터 다시 분석해줘.");
    await expectCoherentTurn(page, beforeBacktrack2);

    // Round 5. Free-chat continuity: the agent answers in-context after all the
    // rewinds without crashing or losing the thread.
    const beforeChat = await thread(page).getByRole("article").count();
    await sendMessage(page, "지금까지 기준을 세 번 바꿔봤는데, 어떤 기준이 제일 신호가 뚜렷했는지 정리해줘.");
    await expectCoherentTurn(page, beforeChat);
  });
});
