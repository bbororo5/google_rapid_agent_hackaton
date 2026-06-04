import { expect, test } from "@playwright/test";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const sampleMetricsCsv = path.join(root, "apps/frontend/fixtures/sample-channel-metrics.csv");
const screenshotDir = "/Users/seonung/.gemini/antigravity/brain/e0d005fe-2b1d-406e-b98c-1354825d54f8";

test.describe("visual qa screenshot flow", () => {
  test("runs through the application taking screenshots", async ({ page }) => {
    test.setTimeout(90000);
    // 1. Initial State
    await page.goto("http://localhost:3000/");
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(screenshotDir, "01-initial-state.png"), fullPage: true });

    // 2. CSV Selected State
    await page.getByLabel(/csv/i).setInputFiles(sampleMetricsCsv);
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotDir, "02-csv-selected.png"), fullPage: true });

    // 3. Trigger "Run Analysis" & Observe Loading Checklist State
    await page.getByRole("button", { name: /send|analy[sz]e|run analysis/i }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotDir, "03-loading-checklist.png"), fullPage: true });

    // 4. Wait for analysis to complete and show results page (with signals table, hypotheses, inline CTA)
    await expect(page.getByText("BTS shorts outperformed recent baseline")).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotDir, "04-results-ready.png"), fullPage: true });

    // 5. Click inline CTA to slide open drawer (Desktop Preview)
    await page.getByRole("button", { name: /review & edit campaign spec/i }).click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotDir, "05-spec-drawer-desktop.png"), fullPage: true });

    // 6. Toggle Mobile View
    await page.getByTitle("Mobile Preview").click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotDir, "06-spec-drawer-mobile.png"), fullPage: true });

    // Switch back to desktop view for completeness or code view
    await page.getByTitle("Desktop Preview").click();
    await page.waitForTimeout(200);

    // 7. Toggle Code View Tab
    await page.getByRole("button", { name: /코드/i }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotDir, "07-spec-drawer-code.png"), fullPage: true });

    // Switch back to preview tab to click Approve
    await page.getByRole("button", { name: /미리보기/i }).click();
    await page.waitForTimeout(200);

    // 8. Edit title input and approve experiments
    const titleInput = page.getByRole("textbox", { name: /experiment title|title/i });
    await titleInput.fill("BTS face-first hook test edited");
    await page.getByRole("button", { name: /approve experiments|approve/i }).click();
    
    // Wait for the drawer to close & receipt to show in chat stream
    await expect(page.getByText("BTS face-first hook test edited").first()).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotDir, "08-approved-receipt.png"), fullPage: true });
  });
});
