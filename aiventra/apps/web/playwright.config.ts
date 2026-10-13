import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./tests/support/registry-guard.ts",
  globalTeardown: "./tests/support/registry-teardown.ts",
  timeout: 60000,
  expect: { timeout: 15000 },
  use: {
    baseURL: "http://localhost:3002",
    viewport: { width: 1440, height: 1100 },
    trace: "off",
  },
  workers: 1,
  reporter: "list",
  webServer: [
    {
      command: `"${resolve(process.env.BROWSER_FIXTURE_PYTHON || "../../.venv/Scripts/python.exe")}" "${resolve("../../scripts/browser_fixture.py")}"`,
      url: "http://127.0.0.1:8002/health/ready",
      timeout: 180000,
      reuseExistingServer: false,
    },
    {
      command:
        "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3002",
      url: "http://localhost:3002",
      timeout: 120000,
      reuseExistingServer: false,
      env: {
        API_INTERNAL_URL: "http://127.0.0.1:8002",
        AIVENTRA_TEST_BUILD: "browser",
        WEB_ORIGIN: "http://localhost:3002",
        COOKIE_SECURE: "false",
      },
    },
  ],
});
