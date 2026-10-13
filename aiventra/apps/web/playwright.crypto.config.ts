import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
export default defineConfig({
  testDir: "./tests-crypto",
  globalSetup: "./tests/support/registry-guard.ts",
  globalTeardown: "./tests/support/registry-teardown.ts",
  workers: 1,
  timeout: 120000,
  expect: { timeout: 30000 },
  use: {
    baseURL: "http://localhost:3004",
    viewport: { width: 1440, height: 1100 },
    trace: "off",
  },
  reporter: "list",
  webServer: [
    {
      command: `"${resolve(process.env.BROWSER_FIXTURE_PYTHON || "../../.venv/Scripts/python.exe")}" "${resolve("../../scripts/crypto_browser_fixture.py")}"`,
      url: "http://127.0.0.1:8004/health/ready",
      timeout: 180000,
      reuseExistingServer: false,
    },
    {
      command:
        "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3004",
      url: "http://localhost:3004",
      timeout: 120000,
      reuseExistingServer: false,
      env: {
        API_INTERNAL_URL: "http://127.0.0.1:8004",
        AIVENTRA_TEST_BUILD: "crypto",
        WEB_ORIGIN: "http://localhost:3004",
        COOKIE_SECURE: "false",
      },
    },
  ],
});
