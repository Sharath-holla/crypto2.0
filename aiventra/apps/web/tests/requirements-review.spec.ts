import { expect, test } from "@playwright/test";
import { loginOwner } from "./support/login";

test("no-model wizard saves an owner scope and sign-off without fabricated critique", async ({
  page,
}) => {
  await loginOwner(page.context().request);
  await page.goto("/?view=new-project");
  await page
    .getByLabel("Project name", { exact: true })
    .fill(`Owner scope browser fixture ${Date.now()}`);
  await page
    .getByLabel("Project requirements", { exact: true })
    .fill(
      "Build a task manager with create, update, complete and delete operations backed by persistent SQLite.",
    );
  await expect(
    page.getByRole("status").filter({ hasText: "Saved · version" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "3 Review", exact: true }).click();
  await page
    .getByRole("button", { name: "Submit requirements", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Review and refine requirements",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(/No model critique exists for this scope version/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Approve exact requirements version 1",
      exact: true,
    }),
  ).toBeDisabled();
  await page
    .getByLabel("Scope acceptance criteria", { exact: true })
    .fill(
      "CRUD operations persist after restart.\nInvalid input leaves stored tasks unchanged.",
    );
  await page
    .getByRole("button", { name: "Save reviewed scope version", exact: true })
    .click();
  await expect(
    page.getByText("Requirements version 2 · owner authored", { exact: true }),
  ).toBeVisible();
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
  const id = new URL(page.url()).searchParams.get("draft");
  const record = await (
    await page.context().request.get(`/api/project-drafts/${id}`)
  ).json();
  const state = await (await page.context().request.get("/api/state")).json();
  expect(
    state.runs.filter(
      (run: { workflow_id: string }) => run.workflow_id === record.workflow.id,
    ),
  ).toHaveLength(0);
  expect(record.approved_project_id).toBeNull();
  await page.reload();
  await expect(
    page.getByText("requirements approved", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
