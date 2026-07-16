import { defineConfig, devices } from "@playwright/test";

const localBaseURL = "http://localhost:5173";
const configuredBaseURL = process.env.PLAYWRIGHT_BASE_URL;
const baseURL = configuredBaseURL ?? localBaseURL;
const usesExternalServer = Boolean(
  configuredBaseURL && configuredBaseURL !== localBaseURL
);
const webServer = process.env.PLAYWRIGHT_SKIP_WEBSERVER === "1" || usesExternalServer
  ? undefined
  : {
      command:
        "VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --host localhost --port 5173",
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000
    };

export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI
    ? [["line"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : "list",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL,
    screenshot: "only-on-failure",
    trace: "on-first-retry"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ],
  webServer
});
