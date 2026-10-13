import { testOrigin } from "./support/environment";
import { test, expect } from "@playwright/test";
import { loginOwner } from "./support/login";
import type { State } from "../src/lib/types";

test("saved BA CTO PM fixture creates documents and an unapproved workforce revision", async ({
  page,
}) => {
  test.setTimeout(180000);
  const request = page.context().request;
  const headers = { Origin: testOrigin };
  await loginOwner(request);
  const state: State = await (await request.get("/api/state")).json();
  const title = `Planning browser fixture ${Date.now()}`;
  const requirement = await (
    await request.post("/api/requirements", {
      headers,
      data: {
        client_id: state.clients[0].id,
        title,
        text: "Document requirements and architecture for a small inventory service. Explicit deterministic browser fixture.",
        mode: "mock",
        budget_micro: 5000000,
      },
    })
  ).json();
  let proposal: State["proposals"][number] | undefined;
  await expect
    .poll(
      async () => {
        const current: State = await (await request.get("/api/state")).json();
        proposal = current.proposals.find(
          (p) => p.requirement_id === requirement.id,
        );
        return !!proposal;
      },
      { timeout: 60000 },
    )
    .toBe(true);
  const approved = await request.post(
    `/api/proposals/${proposal!.id}/approve`,
    {
      headers,
      data: {
        version: proposal!.version,
        content_hash: proposal!.content_hash,
        selection: proposal!.content.recommendation,
      },
    },
  );
  expect(approved.status()).toBe(200);
  const project = await approved.json();
  await page.goto("/?view=meetings");
  await page
    .getByRole("button", { name: "BA → CTO → PM plan", exact: true })
    .click();
  await page
    .getByLabel("Approved project", { exact: true })
    .selectOption(project.id);
  await page
    .getByLabel("Agent work provider mode", { exact: true })
    .selectOption("mock");
  await page
    .getByLabel("Planning objective", { exact: true })
    .fill(
      "Create a traceable plan using the saved requirements and architecture documents.",
    );
  await page
    .getByRole("button", { name: "Start saved planning workflow", exact: true })
    .click();
  let work: State["agent_work"][number] | undefined;
  await expect
    .poll(
      async () => {
        const current: State = await (await request.get("/api/state")).json();
        work = current.agent_work.find(
          (w) => w.project_id === project.id && w.kind === "planning",
        );
        return current.workflows.find((w) => w.id === work?.workflow_id)
          ?.status;
      },
      { timeout: 60000 },
    )
    .toBe("completed");
  expect(work!.result.approval_required).toBe(true);
  expect(work!.result.mode).toBe("mock");
  const draft = await (
    await request.get(`/api/projects/${project.id}/staffing`)
  ).json();
  expect(draft.version).toBe(2);
  expect(draft.status).toBe("draft");
  expect(draft.tasks).toEqual([]);
  await page.reload();
  const row = page
    .locator("details")
    .filter({ hasText: title })
    .filter({ hasText: "planning" })
    .first();
  await row.locator("summary").click();
  await expect(
    row.getByText("Business Analyst → CTO", { exact: false }),
  ).toBeVisible();
  await row
    .getByRole("button", { name: "Review workforce draft", exact: true })
    .click();
  await page
    .getByLabel("Staffing project", { exact: true })
    .selectOption(project.id);
  await expect(
    page.getByRole("heading", { name: "Team proposal · v2", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve exact workforce", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/agent-planning-fixture.png",
    fullPage: true,
  });
});
