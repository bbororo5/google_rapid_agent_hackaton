import { expect, test } from "@playwright/test";

test.describe("conversation-first mock server", () => {
  test("starts a thread from plain chat and keeps chat open for follow-up messages", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이번 캠페인 뭐부터 보면 좋을까?");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByText(/이번 캠페인 뭐부터/i)).toBeVisible();
    await expect(page.getByText(/우선 저장률과 댓글 전환/i)).toBeVisible();

    await page.getByRole("textbox", { name: /message/i }).fill("리텐션 관점으로 이어서 봐줘.");
    await expect(page.getByRole("button", { name: /^send$/i })).toBeEnabled();
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/리텐션 관점이면/i)).toBeVisible();
  });

  test("opens the right panel when a markdown document block arrives", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("근거 문서 보여줘");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByRole("button", { name: /open evidence notes/i })).toBeVisible();
    await expect(page.getByRole("region", { name: /evidence notes/i })).toBeVisible();
    await expect(page.getByRole("complementary").last()).toContainText("Evidence notes");
  });

  test("lets the agent raise signal and approval blocks from natural chat", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByText(/two BTS shorts that outperformed/i).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: /use this signal/i })).toBeVisible();

    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.getByText(/experiment plan is ready for review/i).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /approve experiments|approve/i })).toBeVisible();
  });

  test("accepts natural-language approval and revision requests through message.send", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.getByRole("button", { name: /approve experiments|approve/i })).toBeVisible();

    await page.getByRole("textbox", { name: /message/i }).fill("두 번째 실험은 빼줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/두 번째 실험은 제외/i)).toBeVisible();

    await page.getByRole("textbox", { name: /message/i }).fill("승인할게");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/human approval processed|approval complete|calendar/i).first()).toBeVisible();
  });
});
