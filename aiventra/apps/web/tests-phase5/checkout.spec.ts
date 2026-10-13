import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { loginAccount } from "../tests/support/login";

test("isolated checkout fixture requires separate approval and retains saved execution controls", async ({
  page,
}) => {
  const fixture = JSON.parse(
    readFileSync("../../data/phase5-browser-state.json", "utf8"),
  );
  const request = page.context().request;
  await loginAccount(
    request,
    {
      email: "phase5-owner@fixture.test",
      password: "phase5-fixture-owner-password",
    },
    "http://localhost:3001",
  );
  await page.goto(
    `/?view=engineering&project=${fixture.packages.acceptance.project_id}`,
  );
  await page
    .getByText("Deterministic checkout UI fixture · read-only findings", {
      exact: true,
    })
    .click();
  const panel = page.getByRole("region", {
    name: "Restricted repository checkout",
  });
  await panel
    .getByRole("button", { name: "Request isolated checkout", exact: true })
    .click();
  await expect(
    panel.getByText("DETERMINISTIC UI FIXTURE; NO GITHUB OR DOCKER EXECUTION", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Run approved tests", exact: true }),
  ).toBeDisabled();
  await panel
    .getByRole("button", { name: "Approve this source for tests", exact: true })
    .click();
  await expect(
    panel.getByRole("button", { name: "Run approved tests", exact: true }),
  ).toBeEnabled();
  await panel.getByLabel("Checkout test suite").selectOption("node-test");
  await expect(
    panel.getByRole("button", { name: "Run approved tests", exact: true }),
  ).toBeDisabled();
  await panel
    .getByRole("button", { name: "Approve this source for tests", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "Run approved tests", exact: true })
    .click();
  await expect(
    panel.getByText("Execution: completed", { exact: true }),
  ).toBeVisible();
  await panel
    .getByRole("button", { name: "Refresh saved execution", exact: true })
    .click();
  await expect(panel).toContainText(
    "DETERMINISTIC RUNNER ADAPTER; NO GITHUB OR DOCKER EXECUTION",
  );
  await page.reload();
  await page
    .getByText("Deterministic checkout UI fixture · read-only findings", {
      exact: true,
    })
    .click();
  await expect(
    panel.getByRole("button", { name: "Run approved tests", exact: true }),
  ).toBeDisabled();
  await panel
    .getByRole("button", { name: "Load saved executions", exact: true })
    .click();
  await panel
    .getByLabel("Saved checkout executions")
    .getByRole("button")
    .click();
  await expect(
    panel.getByText("Execution: completed", { exact: true }),
  ).toBeVisible();
  await panel
    .getByRole("button", { name: "Refresh checkout receipt", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "Clean up checkout", exact: true })
    .click();
  await expect(panel.getByText(/cleaned · main/)).toBeVisible();
  await expect(
    panel.getByRole("button", {
      name: "Approve this source for tests",
      exact: true,
    }),
  ).toHaveCount(0);
});
