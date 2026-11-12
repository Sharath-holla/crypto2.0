import { test, expect } from "@playwright/test";
import { loginOwner } from "./support/login";

test("local model diagnostics use backend state and send no inference", async ({
  page,
}) => {
  await loginOwner(page.context().request);
  const request = page.context().request;
  await page.goto("/?view=models");
  await page
    .getByRole("button", { name: "Provider connections", exact: true })
    .click();
  await page.getByRole("button", { name: "Add provider", exact: true }).click();
  await page
    .getByLabel("Provider name", { exact: true })
    .fill("Ollama browser diagnostics fixture");
  await page
    .getByRole("combobox", { name: "Adapter type", exact: true })
    .selectOption("ollama");
  await expect(
    page.getByLabel("Server credential variable name", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText(
      "Local Ollama uses no API key. Keep the server on loopback.",
      { exact: true },
    ),
  ).toBeVisible();
  const registered = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/providers") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Register provider", exact: true })
    .click();
  expect((await registered).status()).toBe(201);
  const before = await (await request.get("/api/state")).json();
  expect(before.runtime.isolated_test_environment).toBe(true);
  await page.goto("/?view=models");
  const card = page
    .locator(".provider-card")
    .filter({ hasText: "Ollama browser diagnostics fixture" });
  await card
    .getByRole("button", { name: "Check local server", exact: true })
    .click();
  // The private browser backend prohibits all real outbound connections,
  // including the owner's Ollama daemon. Its unavailable response is real.
  await expect(
    card.getByText("Local server unavailable", { exact: true }),
  ).toBeVisible();
  await expect(
    card.getByText("No installed local models were observed.", { exact: true }),
  ).toBeVisible();
  await expect(
    card.getByText(
      "Local Ollama diagnostics unavailable; no inference was sent",
      { exact: true },
    ),
  ).toBeVisible();
  const after = await (await request.get("/api/state")).json();
  expect(after.runs.length).toBe(before.runs.length);
  expect(after.models.length).toBe(before.models.length);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
