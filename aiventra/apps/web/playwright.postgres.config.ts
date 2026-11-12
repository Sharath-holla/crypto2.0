import { defineConfig } from "@playwright/test";
import ordinary from "./playwright.config";

if (
  process.env.CI !== "true" ||
  !/^browser_ci_\d+_\d+$/.test(process.env.BROWSER_CI_DATABASE || "")
)
  throw new Error(
    "PostgreSQL browser tests require the dedicated disposable CI profile",
  );
process.env.BROWSER_TEST_ORIGIN = "http://localhost:3000";
export default defineConfig({
  ...ordinary,
  use: { ...ordinary.use, baseURL: "http://localhost:3000" },
  webServer: undefined,
  globalSetup: "./tests/support/postgres-guard.ts",
  globalTeardown: undefined,
});
