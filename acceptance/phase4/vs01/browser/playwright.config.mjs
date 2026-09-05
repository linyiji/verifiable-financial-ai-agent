import { defineConfig, devices } from "@playwright/test";

const frontendUrl = process.env.VS01_FRONTEND_URL ?? "http://127.0.0.1:4173";
const outputRoot = process.env.VS01_BROWSER_ARTIFACT_DIR ?? "artifacts";

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.real.spec.mjs",
  outputDir: `${outputRoot}/test-results`,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [
    ["line"],
    ["json", { outputFile: `${outputRoot}/playwright-result.json` }],
    ["html", { outputFolder: `${outputRoot}/html`, open: "never" }]
  ],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: frontendUrl,
    browserName: "chromium",
    viewport: { width: 1366, height: 900 },
    deviceScaleFactor: 1,
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    serviceWorkers: "block",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  projects: [{ name: "chromium-vs01" }]
});
