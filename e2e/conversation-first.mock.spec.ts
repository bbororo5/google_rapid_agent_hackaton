import { expect, test } from "@playwright/test";

test.describe("conversation-first mock server", () => {
  test("supports free chat and composer shortcuts", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    const composer = page.getByRole("textbox", { name: /message/i });

    await composer.fill("첫 줄");
    await composer.press("Shift+Enter");
    await composer.type("둘째 줄");
    await expect(composer).toHaveValue("첫 줄\n둘째 줄");

    await composer.press("Enter");
    await expect(page.getByText("첫 줄")).toBeVisible();
    await expect(page.getByText("둘째 줄")).toBeVisible();
    await expect(composer).toHaveValue("");

    await composer.fill("리텐션 관점으로 이어서 봐줘.");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/리텐션 관점이면/i)).toBeVisible();
  });

  test("opens saved outputs from the right drawer", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("근거 문서 보여줘");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByRole("button", { name: /open evidence notes/i })).toBeVisible();
    await expect(page.getByRole("region", { name: /evidence notes/i })).toBeVisible();
    await expect(page.getByRole("complementary", { name: /output panel/i })).toContainText("Evidence notes");
    await expect(page.getByRole("button", { name: /markdown document evidence notes/i })).toBeVisible();

    await page.getByRole("textbox", { name: /message/i }).fill("문서보여줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/문서를 다시 열어둘게요/).first()).toBeVisible();
  });

  test("keeps agent outputs inline while archiving them", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByText(/two BTS shorts that outperformed/i).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: /use this signal/i })).toBeVisible();

    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.locator(".thread-gate-inline", { hasText: /Signal Review/ }).filter({ hasText: /Completed/ })).toBeVisible();
    await page.getByRole("button", { name: /show details panel/i }).click();
    await expect(page.getByRole("button", { name: /confirmed signal bts shorts outperformed recent baseline/i })).toBeVisible();

    await expect(page.getByRole("button", { name: /approve experiments|approve/i })).toBeVisible({ timeout: 15000 });
    await page.getByRole("textbox", { name: /message/i }).fill("두 번째 실험은 빼고 승인할게");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/approval complete|human approval processed|calendar/i).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: /approved output approval complete/i })).toBeVisible();

    await page.getByRole("textbox", { name: /message/i }).fill("마음에들어");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/마음에들어/)).toBeVisible();

    const order = await page.evaluate(() => {
      const rows = [...document.querySelectorAll(".thread-scroll > article, .thread-scroll > section.thread-gate-inline")].map((element, index) => ({
        index,
        text: element.textContent ?? "",
        isAssistant: element.classList.contains("assistant-flow-message"),
      }));
      const approvalIndex = rows.find((row) => row.text.includes("Approval complete"))?.index ?? -1;
      const userIndex = rows.find((row) => row.text.includes("마음에들어"))?.index ?? -1;
      const assistantAfterIndex = rows.find((row) => row.index > userIndex && row.isAssistant)?.index ?? -1;
      const laterApprovalIndex = rows.find((row) => row.index > userIndex && row.text.includes("Approval complete"))?.index ?? -1;
      return { approvalIndex, userIndex, assistantAfterIndex, laterApprovalIndex };
    });

    expect(order.approvalIndex).toBeGreaterThanOrEqual(0);
    expect(order.userIndex).toBeGreaterThan(order.approvalIndex);
    expect(order.assistantAfterIndex).toBeGreaterThan(order.userIndex);
    expect(order.laterApprovalIndex).toBe(-1);
  });
});
