import { testOrigin } from "./support/environment";
import { fixtureSetting as setting } from "./support/environment";
import { test, expect } from "@playwright/test";

const headers = { Origin: testOrigin };

test("workforce UI edits exact staffing, approves real tasks, pauses and recovers saved state", async ({
  page,
}) => {
  test.setTimeout(180000);
  const request = page.context().request;
  await expect
    .poll(
      async () => {
        const response = await request.post("/api/auth/login", {
          headers,
          data: {
            email: setting("OWNER_EMAIL"),
            password: setting("OWNER_PASSWORD"),
          },
        });
        expect([200, 429]).toContain(response.status());
        return response.status();
      },
      { timeout: 75000, intervals: [10000] },
    )
    .toBe(200);
  const state = await (await request.get("/api/state")).json();
  const name = `Workforce browser fixture ${Date.now()}`;
  const requirement = await (
    await request.post("/api/requirements", {
      headers,
      data: {
        client_id: state.clients[0].id,
        title: name,
        text: "Build web dashboard frontend and backend API with PostgreSQL database. Explicit deterministic browser fixture.",
        mode: "mock",
        budget_micro: 5000000,
      },
    })
  ).json();
  let proposal: {
    id: string;
    version: number;
    content_hash: string;
    content: { recommendation: string };
  };
  await expect
    .poll(async () => {
      const value = await (await request.get("/api/state")).json();
      proposal = value.proposals.find(
        (p: { requirement_id: string }) => p.requirement_id === requirement.id,
      );
      return !!proposal;
    })
    .toBe(true);
  const projectResponse = await request.post(
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
  expect(projectResponse.status()).toBe(200);
  const project = await projectResponse.json();
  await page.goto("/?view=allocation");
  await page
    .getByLabel("Staffing project", { exact: true })
    .selectOption(project.id);
  await expect(
    page.getByRole("heading", { name: "Team proposal · v1", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Staffing adapter", { exact: true })
    .selectOption("mock");
  await page.getByLabel("Staffing concurrency", { exact: true }).fill("1");
  await page
    .getByLabel("Task model selection mode", { exact: true })
    .selectOption("hybrid");
  await page
    .getByRole("button", { name: "Save workforce changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Team proposal · v2", exact: true }),
  ).toBeVisible();
  const requirementCard = page.locator("details.allocation-task").filter({
    has: page.getByLabel("Objective requirements", { exact: true }),
  });
  await requirementCard.locator(":scope > summary").click();
  const taskModel = page.getByLabel("Model requirements", { exact: true });
  await expect(taskModel.locator("option").nth(1)).toBeAttached();
  const modelId = await taskModel
    .locator("option")
    .nth(1)
    .getAttribute("value");
  expect(modelId).toBeTruthy();
  await taskModel.selectOption(modelId!);
  await page
    .getByRole("button", { name: "Save workforce changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Team proposal · v3", exact: true }),
  ).toBeVisible();
  await expect(
    requirementCard.getByText(
      "Exact owner model choice passed task and zero-cost filters",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve exact workforce", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Pause workforce", exact: true }),
  ).toBeVisible();
  await expect
    .poll(async () => {
      const value = await (
        await request.get(`/api/projects/${project.id}/staffing`)
      ).json();
      return value.tasks.filter(
        (t: { kind: string; status: string; payload: { plan_key: string } }) =>
          t.kind === "document" &&
          t.payload.plan_key !== "security" &&
          t.status !== "completed",
      ).length;
    })
    .toBe(0);
  await page
    .getByRole("button", { name: "Pause workforce", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Resume workforce", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByLabel("Staffing project", { exact: true })
    .selectOption(project.id);
  await expect(
    page.getByRole("button", { name: "Resume workforce", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Resume workforce", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Pause workforce", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Resume workforce", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
  await page
    .getByRole("heading", { name: "Team proposal · v3", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../../artifacts/staffing-mobile.png",
    animations: "disabled",
  });
});
