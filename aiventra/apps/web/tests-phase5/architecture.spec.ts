import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { loginAccount } from "../tests/support/login";

test("saved CTO options and exact owner selection persist in the project", async ({
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
  await page.goto("/?view=proposals");
  await page
    .getByRole("row")
    .filter({ hasText: "Task Management Web Application" })
    .getByRole("button", { name: "Review", exact: true })
    .click();
  const evidence = page.getByRole("region", {
    name: "Saved architecture evidence",
  });
  await expect(evidence).toBeVisible();
  await expect(
    evidence.getByText("FIXTURE_TESTED", { exact: true }),
  ).toBeVisible();
  await evidence
    .getByText("Separated API and web client · design and trade-offs", {
      exact: true,
    })
    .click();
  await expect(
    evidence.getByRole("heading", { name: "high level design", exact: true }),
  ).toBeVisible();
  await evidence
    .getByText("Saved document identities and hashes", { exact: true })
    .click();
  const state = await (await request.get("/api/state")).json();
  const proposal = state.proposals.find(
    (row: { id: string }) => row.id === fixture.architecture_proposal_id,
  );
  expect(proposal.content.architecture_manifest.documents).toHaveLength(2);
  await expect(evidence).toContainText(
    proposal.content.architecture_manifest.documents[0].sha256,
  );
  await page
    .getByRole("button")
    .filter({
      has: page.getByRole("heading", {
        name: "Separated API and web client",
        exact: true,
      }),
    })
    .click();
  await page
    .getByRole("button", { name: "Approve selected solution", exact: false })
    .click();
  await expect(page).toHaveURL(/view=projects/);
  await page
    .getByRole("button", { name: "Open Requirements stage", exact: true })
    .click();
  await expect(
    page.getByText("Selected architecture: Separated API and web client", {
      exact: true,
    }),
  ).toBeVisible();
  const after = await (await request.get("/api/state")).json();
  const project = after.projects.find(
    (row: { proposal_id: string }) => row.proposal_id === proposal.id,
  );
  expect(project.selected_alternative).toBe("Separated API and web client");
  await page
    .getByRole("button", { name: "Open QA & review stage", exact: true })
    .click();
  const quality = page.getByRole("region", {
    name: "Three-stage quality assurance",
    exact: true,
  });
  await expect(quality).toBeVisible();
  for (const label of [
    "Implementation Verification",
    "Independent Functional QA",
    "Security & Release Verification",
  ]) {
    await expect(
      quality.getByText(new RegExp(`Round [123] — ${label}`)),
    ).toBeVisible();
  }
  await expect(
    quality.getByRole("heading", { name: "Release blockers", exact: true }),
  ).toBeVisible();
  const frozenResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/projects/${project.id}/quality-readiness`) &&
      response.request().method() === "POST",
  );
  await quality
    .getByRole("button", { name: "Save readiness report", exact: true })
    .click();
  const frozen = await frozenResponse;
  expect(frozen.status()).toBe(201);
  const savedReadiness = await frozen.json();
  expect(savedReadiness.data.evaluation.manifest.production_ready).toBe(false);
  expect(savedReadiness.data.evaluation.ready).toBe(false);
  expect(savedReadiness.data.artifact_hash).toMatch(/^[a-f0-9]{64}$/);
  await quality
    .getByText("Requirement traceability and exact evidence versions", {
      exact: true,
    })
    .click();
  await expect(quality).toContainText('"production_ready": false');
  await page.reload();
  await page
    .getByRole("button", { name: "Open QA & review stage", exact: true })
    .click();
  await expect(
    page.getByRole("region", {
      name: "Three-stage quality assurance",
      exact: true,
    }),
  ).toContainText("No engineering candidate has been independently verified");
  await page.reload();
  await page
    .getByRole("button", { name: "Open Requirements stage", exact: true })
    .click();
  await expect(
    page.getByText("Selected architecture: Separated API and web client", {
      exact: true,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
