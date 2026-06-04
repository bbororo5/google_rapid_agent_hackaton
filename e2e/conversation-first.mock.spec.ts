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

  test("sends on Enter while Shift+Enter keeps a multiline draft", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    const composer = page.getByRole("textbox", { name: /message/i });
    await composer.fill("첫 줄");
    const initialHeight = await composer.evaluate((element) => element.getBoundingClientRect().height);

    await composer.press("Shift+Enter");
    await composer.type("둘째 줄");
    const multilineHeight = await composer.evaluate((element) => element.getBoundingClientRect().height);
    await expect(composer).toHaveValue("첫 줄\n둘째 줄");
    expect(multilineHeight).toBeGreaterThan(initialHeight);

    await composer.press("Enter");
    await expect(page.getByText("첫 줄")).toBeVisible();
    await expect(page.getByText("둘째 줄")).toBeVisible();
    await expect(composer).toHaveValue("");
  });

  test("caps composer growth and scrolls long drafts", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    const composer = page.getByRole("textbox", { name: /message/i });
    await composer.fill(Array.from({ length: 12 }, (_, index) => `line ${index + 1}`).join("\n"));
    const metrics = await composer.evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      overflowY: window.getComputedStyle(element).overflowY,
    }));

    expect(metrics.clientHeight).toBeLessThanOrEqual(112);
    expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);
    expect(metrics.overflowY).toBe("auto");
  });

  test("opens the right panel when a markdown document block arrives", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("근거 문서 보여줘");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByRole("button", { name: /open evidence notes/i })).toBeVisible();
    await expect(page.getByRole("region", { name: /evidence notes/i })).toBeVisible();
    await expect(page.getByRole("complementary", { name: /output panel/i })).toContainText("Evidence notes");
    await expect(page.getByRole("button", { name: /markdown document evidence notes/i })).toBeVisible();

    await page.getByRole("textbox", { name: /message/i }).fill("문서");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/문서를 다시 열어둘게요/)).toHaveCount(2);
  });

  test("answers document-keyword chat after an analysis stream has already emitted a document", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByRole("region", { name: /evidence notes/i })).toBeVisible({ timeout: 15000 });

    await page.getByRole("textbox", { name: /message/i }).fill("문서보여줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/문서를 다시 열어둘게요/)).toBeVisible();
  });

  test("lets the agent raise signal and approval blocks from natural chat", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByText(/two BTS shorts that outperformed/i).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: /use this signal/i })).toBeVisible();

    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.locator(".thread-gate-inline", { hasText: /Signal Review/ }).filter({ hasText: /Completed/ })).toBeVisible();
    await page.getByRole("button", { name: /show details panel/i }).click();
    await expect(page.getByRole("button", { name: /confirmed signal bts shorts outperformed recent baseline/i })).toBeVisible();
    await page.getByRole("button", { name: /confirmed signal bts shorts outperformed recent baseline/i }).click();
    await expect(page.getByRole("complementary", { name: /output panel/i })).toContainText("Evidence refs");

    await expect(page.getByText(/experiment plan is ready for review/i).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /approve experiments|approve/i })).toBeVisible();
  });

  test("places follow-up chat after the active signal decision", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByRole("button", { name: /use this signal/i })).toBeVisible({ timeout: 15000 });

    await page.getByRole("textbox", { name: /message/i }).fill("이제 이 시그널 기준으로 카피만 좁혀줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/이제 이 시그널 기준/)).toBeVisible();

    const order = await page.evaluate(() => {
      const rows = [...document.querySelectorAll(".thread-scroll > article, .thread-scroll > section.thread-gate-inline")].map((element, index) => ({
        index,
        text: element.textContent ?? "",
      }));
      const signalIndex = rows.find((row) => row.text.includes("Signal Review"))?.index ?? -1;
      const userIndex = rows.find((row) => row.text.includes("이제 이 시그널 기준"))?.index ?? -1;
      return { signalIndex, userIndex };
    });

    expect(order.signalIndex).toBeGreaterThanOrEqual(0);
    expect(order.userIndex).toBeGreaterThan(order.signalIndex);
  });

  test("keeps pre-approval follow-up before the experiment approval gate", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByRole("button", { name: /use this signal/i })).toBeVisible({ timeout: 15000 });

    await page.getByRole("textbox", { name: /message/i }).fill("ㅁㄴㅇㄹ아");
    await page.getByRole("button", { name: /^send$/i }).click();
    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.getByRole("button", { name: /approve experiments|approve/i })).toBeVisible({ timeout: 15000 });

    const order = await page.evaluate(() => {
      const rows = [...document.querySelectorAll(".thread-scroll > article, .thread-scroll > section.thread-gate-inline")].map((element, index) => ({
        index,
        text: element.textContent ?? "",
      }));
      const userIndex = rows.find((row) => row.text.includes("ㅁㄴㅇㄹ아"))?.index ?? -1;
      const planIndex = rows.find((row) => row.text.includes("experiment plan is ready"))?.index ?? -1;
      const approvalIndex = rows.find((row) => row.text.includes("Experiment Approval"))?.index ?? -1;
      return { userIndex, planIndex, approvalIndex };
    });

    expect(order.userIndex).toBeGreaterThanOrEqual(0);
    expect(order.planIndex).toBeGreaterThan(order.userIndex);
    expect(order.approvalIndex).toBeGreaterThan(order.planIndex);
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

  test("places post-approval chat after the approval receipt summary", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /message/i }).fill("이 데이터에서 이상한 점 찾아줘");
    await page.getByRole("button", { name: /^send$/i }).click();
    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.getByRole("button", { name: /approve experiments|approve/i })).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: /approve experiments|approve/i }).click();
    await expect(page.getByText(/approval complete|human approval processed|calendar/i).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole("textbox", { name: /message/i }).fill("마음에들어");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/마음에들어/)).toBeVisible();
    await page.waitForFunction(() => document.querySelectorAll(".assistant-flow-message").length >= 2);

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
