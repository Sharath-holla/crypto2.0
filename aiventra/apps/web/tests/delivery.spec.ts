import { testOrigin } from "./support/environment";
import { test, expect } from "@playwright/test";
import { loginOwner } from "./support/login";
import type { State } from "../src/lib/types";

test("delivery readiness and fixture controls show real backend evidence", async ({
  page,
}) => {
  test.setTimeout(120000);
  const request = page.context().request;
  await loginOwner(request);
  const state: State = await (await request.get("/api/state")).json();
  expect(state.projects.length).toBeGreaterThan(0);
  const project = state.projects[0];
  await page.goto("/?view=projects");
  await page
    .locator("button.portfolio-card")
    .filter({
      has: page.getByRole("heading", { name: project.name, exact: true }),
    })
    .click();
  await page.getByRole("button", { name: "Delivery", exact: true }).click();
  const panel = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "Final review readiness",
      exact: true,
    }),
  });
  for (const mode of ["live", "mock"]) {
    const response = await request.get(
      `/api/projects/${project.id}/delivery-readiness?mode=${mode}`,
    );
    expect(response.status()).toBe(200);
    const evidence = await response.json();
    await panel.getByLabel("Final review execution mode").selectOption(mode);
    await expect(
      panel.getByText(`Source SHA-256: ${evidence.source_hash}`, {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      panel.getByLabel("Final review blockers").locator("li"),
    ).toHaveCount(evidence.blockers.length);
    const pending = state.records.some(
      (row) =>
        row.project_id === project.id &&
        row.kind === "delivery_review" &&
        row.status === "reviewing",
    );
    await expect(
      panel.getByRole("button", { name: "Queue five-role final review" }),
    ).toBeEnabled({ enabled: evidence.ready && !pending });
  }
  await panel.getByRole("button", { name: "Refresh review readiness" }).click();
  await expect(
    panel.getByText("Deterministic fixtures cannot certify live work.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/delivery-readiness.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("approved requirement and workforce reach five persisted fixture reviews through the UI", async ({
  page,
}) => {
  test.setTimeout(240000);
  const request = page.context().request;
  const headers = { Origin: testOrigin };
  await loginOwner(request);
  const state: State = await (await request.get("/api/state")).json();
  const created = await request.post("/api/requirements", {
    headers,
    data: {
      client_id: state.clients[0].id,
      title: `Delivery review browser fixture ${Date.now()}`,
      text: "Document a small business operations plan with requirements, architecture and security. Explicit deterministic workflow fixture.",
      mode: "mock",
      budget_micro: 5000000,
    },
  });
  expect(created.status()).toBe(201);
  const requirement = await created.json();
  let proposal: State["proposals"][number] | undefined;
  await expect
    .poll(
      async () => {
        const current: State = await (await request.get("/api/state")).json();
        proposal = current.proposals.find(
          (row) => row.requirement_id === requirement.id,
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
  const plan = await (
    await request.get(`/api/projects/${project.id}/staffing`)
  ).json();
  const revised = await request.patch(`/api/staffing/${plan.id}`, {
    headers,
    data: {
      version: plan.version,
      content: { ...plan.content, mode: "mock" },
    },
  });
  expect(revised.status()).toBe(200);
  const currentPlan = await revised.json();
  expect(
    (
      await request.post(`/api/staffing/${plan.id}/approve`, {
        headers,
        data: {
          version: currentPlan.version,
          content_hash: currentPlan.content_hash,
        },
      })
    ).status(),
  ).toBe(200);
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `/api/projects/${project.id}/delivery-readiness?mode=mock`,
        );
        return (await response.json()).ready;
      },
      { timeout: 90000 },
    )
    .toBe(true);
  await page.goto("/?view=projects");
  await page
    .locator("button.portfolio-card")
    .filter({
      has: page.getByRole("heading", { name: project.name, exact: true }),
    })
    .click();
  await page.getByRole("button", { name: "Delivery", exact: true }).click();
  await page.getByLabel("Final review execution mode").selectOption("mock");
  await page
    .getByRole("button", { name: "Queue five-role final review" })
    .click();
  let record: State["records"][number] | undefined;
  await expect
    .poll(
      async () => {
        const current: State = await (await request.get("/api/state")).json();
        record = current.records.find(
          (row) =>
            row.project_id === project.id && row.kind === "delivery_review",
        );
        return record?.status;
      },
      { timeout: 90000 },
    )
    .toBe("fixture_reviewed");
  const current: State = await (await request.get("/api/state")).json();
  const work = current.agent_work.find((row) => row.subject_id === record!.id)!;
  expect(work.result.delivery_released).toBe(false);
  expect(work.result.client_accepted).toBe(false);
  expect(current.projects.find((row) => row.id === project.id)!.status).toBe(
    "active",
  );
  expect(
    current.messages.filter(
      (row) => row.correlation_id === work.id && row.status === "acknowledged",
    ),
  ).toHaveLength(4);
  await page.reload();
  await page
    .locator("button.portfolio-card")
    .filter({
      has: page.getByRole("heading", { name: project.name, exact: true }),
    })
    .click();
  await page.getByRole("button", { name: "Delivery", exact: true }).click();
  const row = page.locator("details").filter({ hasText: record!.title });
  await expect(row.locator(":scope > summary")).toContainText(
    "5/5 saved reviews",
  );
  await row.locator(":scope > summary").click();
  await expect(
    row.getByText("fixture_reviewed", { exact: false }),
  ).toBeVisible();
});
