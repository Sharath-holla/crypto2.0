import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { loginAccount } from "../tests/support/login";

test("deterministic critiques require explicit decisions, revision and exact owner sign-off", async ({
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
  const id = fixture.requirements_review_draft_id;
  await page.goto(`/?view=new-project&draft=${id}`);
  await expect(
    page.getByRole("heading", {
      name: "Review and refine requirements",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Lead AI critique · FIXTURE_TESTED", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Business Analyst critique · FIXTURE_TESTED", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Write a manual plan", exact: true }),
  ).not.toBeVisible();
  const scopeBefore = await (
    await request.get(`/api/project-drafts/${id}/requirements-review`)
  ).json();
  expect(scopeBefore.current.version).toBe(1);
  expect(scopeBefore.approved).toBe(false);
  await page
    .getByLabel("Decision for recommendation 1", { exact: true })
    .selectOption("accept");
  await page
    .getByLabel("Reason for recommendation 1", { exact: true })
    .fill("Explicit validation required for acceptance.");
  await page
    .getByLabel("Decision for recommendation 2", { exact: true })
    .selectOption("reject");
  await page
    .getByLabel("Reason for recommendation 2", { exact: true })
    .fill(
      "Duplicate validation recommendation; keep one explicit requirement.",
    );
  for (let index = 1; index <= 4; index++) {
    await page
      .getByLabel(new RegExp(`^Clarification ${index}:`))
      .fill("Task owners, local disposable deployment, no external cost.");
  }
  await page
    .getByLabel("Scope acceptance criteria", { exact: true })
    .fill(
      "Task CRUD persists across restart.\nEmpty titles do not modify saved tasks.",
    );
  await page
    .getByRole("button", { name: "Save reviewed scope version", exact: true })
    .click();
  await expect(
    page.getByText("Requirements version 2 · owner authored", { exact: true }),
  ).toBeVisible();
  const after = await (
    await request.get(`/api/project-drafts/${id}/requirements-review`)
  ).json();
  expect(after.current.scope.functional_requirements).toContain(
    scopeBefore.improvements[0].recommendation,
  );
  expect(
    Object.values(after.current.decisions)
      .map((item) => (item as { action: string }).action)
      .sort(),
  ).toEqual(["accept", "reject"]);
  expect(after.history[0].scope_hash).toBe(scopeBefore.current.scope_hash);
  expect(after.approved).toBe(false);
  await page
    .getByRole("checkbox", { name: /I reviewed this exact saved scope/ })
    .check();
  await page
    .getByRole("button", {
      name: "Approve exact requirements version 2",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("requirements approved", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("requirements approved", { exact: true }),
  ).toBeVisible();
  await page
    .getByText("Requirement version history · 2 saved versions", {
      exact: true,
    })
    .click();
  await expect(page.getByText(/Version 1 · original request/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
