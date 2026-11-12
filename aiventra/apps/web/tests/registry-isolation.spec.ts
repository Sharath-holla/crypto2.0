import { expect, test } from "@playwright/test";
import { loginOwner } from "./support/login";

test("browser contracts use a separate server, owner, vault and registry", async ({
  page,
}) => {
  await loginOwner(page.context().request);
  const state = await (await page.context().request.get("/api/state")).json();
  expect(state.runtime.isolated_test_environment).toBe(true);
  expect(state.runtime.ai_spending_mode).toBe("ZERO_COST_ONLY");
  expect(state.runtime.execution_enabled).toBe(false);
  await page.goto("/?view=new-project");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByText("Preferred Lead AI: GPT-6.1 Sol — Not currently available."),
  ).toBeVisible();
  const picker = page.getByRole("group", { name: "Lead AI", exact: true });
  // A fresh run has no synthetic remote model catalog; other tests may create
  // explicitly labeled fixtures later in this disposable workspace.
  expect(await picker.locator("select").count()).toBe(0);
});
