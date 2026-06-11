import { expect, test, type Locator, type Page } from "@playwright/test";
import path from "node:path";

// Real-stack E2E for ADR-004's state-reactive workflow.
//
// This spec intentionally models LaunchPilot as a round-based war room:
// one user message produces one bounded system reaction. A single analysis
// request must not automatically consume the full analyst -> strategist ->
// writer -> approval pipeline.
//
// This is the default real E2E target for the orchestrator refactor. It is
// expected to fail until the runtime stops treating one analysis request as a
// command to run the full analyst -> strategist -> writer -> approval pipeline.
// Run with:
//
//   E2E_ENV_FILE=.env npm run test:e2e:real

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
  await page.locator("#csv-input").setInputFiles(sampleMetricsCsv);
  const analyzeButton = page.locator("button.composer-action-analyze");
  if (await analyzeButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await analyzeButton.click();
  }
}

function approvalButton(page: Page): Locator {
  return page.getByRole("button", { name: /approve experiments/i });
}

function decisionRegion(page: Page): Locator {
  return page.getByRole("region", { name: /current decision/i });
}

function threadArticles(page: Page): Locator {
  return page.getByRole("region", { name: /campaign agent thread/i }).getByRole("article");
}

async function expectNoApprovalGate(page: Page): Promise<void> {
  await expect(approvalButton(page)).toHaveCount(0);
}

async function expectIntermediateDecisionOnly(page: Page): Promise<void> {
  await expect(decisionRegion(page).first()).toBeVisible({ timeout: ROUND_TIMEOUT });
  await expectNoApprovalGate(page);
}

async function expectAssistantTurnAfter(page: Page, previousArticleCount: number): Promise<void> {
  await expect.poll(async () => await threadArticles(page).count(), { timeout: ROUND_TIMEOUT }).toBeGreaterThan(previousArticleCount + 1);
}

async function expectApprovalGate(page: Page): Promise<void> {
  await expect(approvalButton(page)).toBeVisible({ timeout: ROUND_TIMEOUT });
}

test.describe("real round-based workflow", () => {
  test.describe.configure({ mode: "serial" });

  test("advances by user rounds without cascading phases", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    // Round 1. Free conversation starts the thread, but must not run the phase
    // pipeline just because the user is talking about campaign uncertainty.
    await sendMessage(page, "이번 캠페인 반응이 애매한데, 다음 주에 뭘 테스트하면 좋을지 같이 보고 싶어.");
    await expectNoApprovalGate(page);

    // Round 2. CSV + analysis request should stop at data-analysis output.
    await attachCsvAndAsk(page, "이 CSV로 저장률과 리텐션 관점에서 분석해줘.");
    await expect(page.getByText(/Analyze the campaign metrics I just uploaded/i)).toBeVisible({ timeout: 30_000 });
    await expectIntermediateDecisionOnly(page);

    // Round 3. User can discuss the analysis without forcing hypothesis/plan
    // generation. The system should answer in the current analysis context.
    const beforeAnalysisDiscussion = await threadArticles(page).count();
    await sendMessage(page, "이 분석 신호가 왜 중요하다고 본 거야? 공유 수 관점도 같이 설명해줘.");
    await expectAssistantTurnAfter(page, beforeAnalysisDiscussion);
    await expectNoApprovalGate(page);

    // Round 4. Hypothesis generation happens only when the user asks for it.
    await sendMessage(page, "방금 분석 결과를 바탕으로 원인 가설을 세워줘.");
    await expectIntermediateDecisionOnly(page);

    // Round 5. Hypothesis discussion stays within hypothesis context.
    const beforeHypothesisDiscussion = await threadArticles(page).count();
    await sendMessage(page, "이 가설은 너무 약하지 않아? 업로드 시간 문제일 가능성도 비교해줘.");
    await expectAssistantTurnAfter(page, beforeHypothesisDiscussion);
    await expectNoApprovalGate(page);

    // Round 6. Experiment planning is explicitly requested after the hypothesis
    // conversation, not automatically after analysis.
    await sendMessage(page, "첫 번째 가설을 기준으로 다음 주 실험 계획을 세워줘.");
    await expectApprovalGate(page);

    // Round 7. Plan review and revision happen before persistence.
    await sendMessage(page, "실험 제목을 더 짧게 바꾸고, 실험은 최대 2개만 남겨줘.");
    await expectApprovalGate(page);

    // Round 8. The plan is confirmed. Java owns final persistence.
    await expect(approvalButton(page)).toBeEnabled();
    await approvalButton(page).click();
    const receipt = page.locator(".approval-receipt");
    await expect(receipt.getByText("Human approval processed")).toBeVisible({ timeout: ROUND_TIMEOUT });

    // Round 9. During execution, marketer conversation should be ordinary chat
    // grounded in the approved plan, not a new automatic analysis run.
    const beforeExecutionChat = await threadArticles(page).count();
    await sendMessage(page, "오늘 올릴 콘텐츠 카피를 실험 의도에 맞게 한 줄로 다듬어줘.");
    await expectAssistantTurnAfter(page, beforeExecutionChat);
    await expectNoApprovalGate(page);

    // Round 10. Post-experiment analysis is a new explicit analysis round.
    await attachCsvAndAsk(page, "실험 후 결과 CSV야. 이전에 승인한 실험과 이어서 결과를 분석해줘.");
    await expectIntermediateDecisionOnly(page);

    // Round 11. The user asks for learned insight as free conversation.
    const beforeInsightChat = await threadArticles(page).count();
    await sendMessage(page, "이번 사이클에서 우리가 얻은 핵심 인사이트를 정리해줘.");
    await expectAssistantTurnAfter(page, beforeInsightChat);
    await expectNoApprovalGate(page);
  });

  test("can backtrack from planning to analysis without being procedure-bound", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    const beforeOpeningChat = await threadArticles(page).count();
    await sendMessage(page, "이번 캠페인 다음 주 실험까지 단계별로 같이 잡아보자.");
    await expectAssistantTurnAfter(page, beforeOpeningChat);
    await attachCsvAndAsk(page, "이 CSV로 저장률 중심 분석부터 시작해줘.");
    await expectIntermediateDecisionOnly(page);

    await sendMessage(page, "이 분석 결과로 가설을 세워줘.");
    await expectIntermediateDecisionOnly(page);

    await sendMessage(page, "이 가설 기준으로 실험 계획 초안을 만들어줘.");
    await expectApprovalGate(page);

    // ADR-004 backtracking: user can jump from experiment planning back to data
    // analysis by changing the metric. The system should react to state, not the
    // previously expected procedure.
    await sendMessage(page, "잠깐, 저장률 말고 공유 수 기준으로 처음 분석부터 다시 봐줘.");
    await expectIntermediateDecisionOnly(page);
  });
});
