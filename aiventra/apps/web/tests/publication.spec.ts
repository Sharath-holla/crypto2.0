import { test, expect } from "@playwright/test";
import { loginOwner } from "./support/login";
import type { State } from "../src/lib/types";

test("engineering publication controls reflect actual connector configuration and saved candidates", async ({
  page,
}) => {
  test.setTimeout(120000);
  const request = page.context().request;
  await loginOwner(request);
  const configResponse = await request.get("/api/operations/github");
  expect(configResponse.status()).toBe(200);
  const config = await configResponse.json();
  const state: State = await (await request.get("/api/state")).json();
  expect(state.projects.length).toBeGreaterThan(0);
  const project = state.projects[0];
  await page.goto("/?view=engineering");
  await page
    .locator("button.portfolio-card")
    .filter({
      has: page.getByRole("heading", { name: project.name, exact: true }),
    })
    .click();
  await page.getByRole("button", { name: "Engineering", exact: true }).click();
  const panel = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "GitHub draft publication",
      exact: true,
    }),
  });
  await expect(
    panel.getByText(
      config.credential_configured
        ? "Credential configured"
        : "Credential missing",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    panel.getByText(`${config.repositories.length} authorized repositories`, {
      exact: false,
    }),
  ).toBeVisible();
  const eligible = state.tasks.filter(
    (task) =>
      task.project_id === project.id &&
      task.kind === "coding" &&
      task.status === "completed" &&
      task.payload.mode === "live",
  );
  await expect(
    panel.getByLabel("Publication task").locator("option"),
  ).toHaveCount(eligible.length + 1);
  await expect(
    panel.getByRole("button", {
      name: "Prepare exact publication preview",
      exact: true,
    }),
  ).toBeDisabled();
  const publications = state.records.filter(
    (record) =>
      record.kind === "github_publication" && record.project_id === project.id,
  );
  expect(await panel.locator("details").count()).toBe(publications.length);
  await page.screenshot({
    path: "../../artifacts/publication-controls.png",
    fullPage: true,
  });
});
