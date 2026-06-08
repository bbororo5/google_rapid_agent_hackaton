import { expect, test } from "@playwright/test";
import path from "node:path";

// Runs against the REAL stack (docker compose: agent :8000 + backend :8080 +
// frontend :3000, Vertex/Gemini + Elastic). Agent output is non-deterministic,
// so this test asserts only structural selectors and static frontend strings,
// never LLM-generated text.

const root = path.resolve(import.meta.dirname, "..");
const sampleMetricsCsv = path.join(root, "apps/frontend/fixtures/sample-channel-metrics.csv");

// Real multi-agent pipeline takes tens of seconds per turn.
const ANALYSIS_TIMEOUT = 120_000;

test.describe("real conversation -> CSV analysis -> approval", () => {
  test("chats, analyzes the attached CSV, selects 1-2 experiments, and approves", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    const composer = page.locator("#agent-question");
    await expect(composer).toBeVisible();

    // 1) Free conversation first.
    await composer.fill("이번 캠페인 반응이 애매한데, 다음 주에 뭘 테스트하면 좋을지 같이 보고 싶어.");
    await page.locator("button.composer-action-send").click();
    // User bubble echoes locally and the composer clears -> message.send accepted.
    await expect(page.getByText("이번 캠페인 반응이 애매한데", { exact: false })).toBeVisible();
    await expect(composer).toHaveValue("");

    // 2) Attach the CSV and ask to analyze. With an active session, attaching
    // auto-triggers import + the agent run; if the explicit "analyze" primary
    // action is offered instead, click it. Either way the run starts.
    await composer.fill("이 CSV로 저장률과 리텐션 관점에서 분석해줘.");
    await page.locator("#csv-input").setInputFiles(sampleMetricsCsv);
    const analyzeButton = page.locator("button.composer-action-analyze");
    if (await analyzeButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await analyzeButton.click();
    }
    // Confirm the agent run is underway (auto-sent analyze message).
    await expect(page.getByText(/Analyze the campaign metrics I just uploaded/i)).toBeVisible({ timeout: 30_000 });

    // 3) Wait for the agent to stream a reviewable gate (signal or experiments).
    const useSignal = page.getByRole("button", { name: /use this signal/i });
    const approveButton = page.getByRole("button", { name: /approve experiments/i });
    await expect(useSignal.or(approveButton).first()).toBeVisible({ timeout: ANALYSIS_TIMEOUT });

    // Advance through any signal-review gate(s) until the experiment approval
    // gate is reached. Bounded loop guards against an unexpected stall.
    for (let i = 0; i < 5; i += 1) {
      if (await approveButton.isVisible().catch(() => false)) break;
      if (await useSignal.isVisible().catch(() => false)) {
        await useSignal.click();
        await page.waitForTimeout(1000);
        continue;
      }
      await page.waitForTimeout(1500);
    }
    await expect(approveButton).toBeVisible({ timeout: ANALYSIS_TIMEOUT });

    // 4) Keep only 1-2 experiments selected. Uncheck everything past the first two.
    const includes = page.locator("label.experiment-include input[type=checkbox]");
    await expect(includes.first()).toBeVisible();
    const count = await includes.count();
    for (let i = 2; i < count; i += 1) {
      if (await includes.nth(i).isChecked()) {
        await includes.nth(i).uncheck();
      }
    }
    // Guarantee at least one stays selected.
    if (!(await includes.first().isChecked())) {
      await includes.first().check();
    }

    // 5) Approve.
    await expect(approveButton).toBeEnabled();
    await approveButton.click();

    // 6) Static success receipt rendered by the frontend.
    const receipt = page.locator(".approval-receipt");
    await expect(receipt.getByText("Human approval processed")).toBeVisible({ timeout: ANALYSIS_TIMEOUT });
    await expect(receipt).toContainText(/Growth brief/i);
  });
});
