import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.FRONTEND_URL ?? "http://127.0.0.1:3000";
const envFile = process.env.E2E_ENV_FILE ?? ".env";
const quotedEnvFile = JSON.stringify(envFile);
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_SERVER === "true";

export default defineConfig({
  testDir: "./e2e",
  // Mock specs (*.mock.spec.ts) target the retired :8090 mock server; the real
  // stack is brought up via docker compose. Keep the files for scenario markers
  // but never run them here.
  testIgnore: "**/*.mock.spec.ts",
  fullyParallel: true,
  reporter: [["list"]],
  timeout: 420_000,
  expect: { timeout: 15_000 },
  // Bring up the real three-service stack (agent :8000, backend :8080,
  // frontend :3000) using E2E_ENV_FILE or the repo-root .env. First build can
  // take minutes.
  webServer: [
    {
      command: `COMPOSE_ENV_FILE=${quotedEnvFile} docker compose --env-file ${quotedEnvFile} up --build`,
      url: baseURL,
      reuseExistingServer,
      timeout: 600_000,
    },
  ],
  use: {
    baseURL,
    actionTimeout: 15_000,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
