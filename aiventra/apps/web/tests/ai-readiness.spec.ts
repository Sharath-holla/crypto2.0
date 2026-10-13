import { test, expect } from "@playwright/test";
import { loginOwner } from "./support/login";

test("readiness reflects backend facts and refresh never invokes a model", async ({
  page,
}) => {
  await loginOwner(page.context().request);
  const request = page.context().request;
  const before = await (await request.get("/api/state")).json();
  const readiness = await (await request.get("/api/ai-readiness")).json();
  expect(readiness.spending_mode).toBe("ZERO_COST_ONLY");
  expect(readiness.check_invokes_inference).toBe(false);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "AI readiness", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      `${readiness.registered_models} registered · ${readiness.eligible_models} eligible · ${readiness.live_verified_models} live verified`,
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Refresh readiness", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Refresh readiness", exact: true }),
  ).toBeEnabled();
  const after = await (await request.get("/api/state")).json();
  expect(after.runs.length).toBe(before.runs.length);
  expect(after.models.length).toBe(before.models.length);
  expect(after.providers.length).toBe(before.providers.length);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Connect AI Provider", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Models & Providers", exact: true }),
  ).toBeVisible();
});
