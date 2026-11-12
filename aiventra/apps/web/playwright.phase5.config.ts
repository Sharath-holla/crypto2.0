import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
export default defineConfig({
  testDir: "./tests-phase5",
  workers: 1,
  timeout: 120000,
  expect: { timeout: 20000 },
  use: {
    baseURL: "http://localhost:3001",
    viewport: { width: 1440, height: 1100 },
    trace: "off",
  },
  webServer: [
    {
      command: `"${resolve(process.env.PHASE5_FIXTURE_PYTHON || "../../.venv/Scripts/python.exe")}" "${resolve("../../scripts/phase5_browser_fixture.py")}"`,
      url: "http://127.0.0.1:8001/health/ready",
      timeout: 180000,
      reuseExistingServer: false,
    },
    {
      command:
        "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3001",
      url: "http://localhost:3001",
      timeout: 120000,
      reuseExistingServer: false,
      env: {
        API_INTERNAL_URL: "http://127.0.0.1:8001",
        AIVENTRA_TEST_BUILD: "delivery",
        WEB_ORIGIN: "http://localhost:3001",
        COOKIE_SECURE: "false",
      },
    },
  ],
});
