import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { loginAccount } from "../tests/support/login";

test("fixture vault catalogs feed Settings and saved blocked Lead and worker preferences", async ({
  page,
}) => {
  const fixture = JSON.parse(
    readFileSync("../../data/phase5-browser-state.json", "utf8"),
  );
  const request = page.context().request;
  const headers = { Origin: "http://localhost:3001" };
  await loginAccount(
    request,
    {
      email: "phase5-owner@fixture.test",
      password: "phase5-fixture-owner-password",
    },
    "http://localhost:3001",
  );
  await page.goto("/?view=settings");
  await page
    .getByRole("button", { name: "Models & Providers", exact: true })
    .click();
  const panel = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "Models & Providers",
      exact: true,
    }),
  });
  for (const provider of fixture.catalog_providers) {
    const card = panel.locator(".provider-card").filter({
      has: page.getByRole("heading", { name: provider.name, exact: true }),
    });
    await expect(
      card.getByText("Provider configured", { exact: true }),
    ).toBeVisible();
    await expect(
      card.getByText("0 registered models", { exact: true }),
    ).toBeVisible();
    await card
      .getByRole("button", { name: "Discover models", exact: true })
      .click();
    await expect(
      card.getByText("1 registered models", { exact: true }),
    ).toBeVisible();
    await expect(
      card.getByText("Unavailable under free-only mode", { exact: true }),
    ).toBeVisible();
    await expect(
      card.getByText("Live inference unverified", { exact: true }),
    ).toBeVisible();
    await expect(
      card.getByRole("button", { name: "Refresh models", exact: true }),
    ).toBeEnabled();
  }
  await panel
    .getByLabel("Search models", { exact: true })
    .fill("browser-contract-xai");
  await expect(
    panel.getByText("browser-contract-xai", { exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText("browser-contract-openai", { exact: true }),
  ).toHaveCount(0);
  await panel.getByLabel("Search models", { exact: true }).fill("");
  await panel.getByLabel("Show models", { exact: true }).selectOption("ready");
  await expect(
    panel.getByText("browser-contract-openai", { exact: true }),
  ).toHaveCount(0);
  await panel
    .getByLabel("Show models", { exact: true })
    .selectOption("blocked");
  await expect(
    panel.getByText("browser-contract-openai", { exact: true }),
  ).toBeVisible();
  const catalog = await (await request.get("/api/model-catalog")).json();
  await page.screenshot({ path: "../../data/catalog-fixture-desktop.png" });
  const models = fixture.catalog_providers.map((p: { id: string }) =>
    catalog.models.find((m: { provider_id: string }) => m.provider_id === p.id),
  );
  await page.goto("/?view=new-project");
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Model catalog browser contract");
  await page
    .getByLabel("Upload project requirements", { exact: true })
    .setInputFiles({
      name: "requirements.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "Build a saved tracker with explicit owner approval and independent QA.",
      ),
    });
  await expect(
    page.getByText(/requirements.md · parsed and saved/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Choose your Lead AI", exact: true }),
  ).toBeVisible();
  const lead = page.getByRole("group", { name: "Lead AI", exact: true });
  for (const model of models)
    await expect(lead.locator(`input[value="${model.id}"]`)).toHaveCount(1);
  await page
    .getByLabel("AI provider", { exact: true })
    .selectOption(models[1].provider_id);
  await expect(lead.getByRole("radio")).toHaveCount(1);
  await page.getByLabel("AI provider", { exact: true }).selectOption("");
  await page
    .getByLabel("Model availability", { exact: true })
    .selectOption("ready");
  await expect(lead.getByRole("radio")).toHaveCount(0);
  await page
    .getByLabel("Model availability", { exact: true })
    .selectOption("blocked");
  expect(
    (await lead.locator(".model-picker-list").boundingBox())!.height,
  ).toBeLessThanOrEqual(355);
  const keyboardChoice = lead.locator(`input[value="${models[0].id}"]`);
  await keyboardChoice.focus();
  await page.keyboard.press("Space");
  await expect(keyboardChoice).toBeChecked();
  await page
    .getByLabel("Search AI models", { exact: true })
    .fill("browser-contract-openai");
  await expect(lead.getByRole("radio")).toHaveCount(1);
  await lead.locator(`input[value="${models[0].id}"]`).check();
  await page.getByLabel("Search AI models", { exact: true }).fill("");
  await page
    .getByLabel("Specialist allocation", { exact: true })
    .selectOption("manual");
  await page.getByRole("checkbox", { name: /browser-contract-xai/ }).check();
  await page
    .getByRole("radio", {
      name: `Business Analyst model: ${models[1].identifier}`,
      exact: true,
    })
    .check();
  await expect(
    page.getByRole("status").filter({ hasText: "Saved · version" }),
  ).toBeVisible();
  const id = new URL(page.url()).searchParams.get("draft");
  await page.reload();
  await expect(
    page.getByRole("radio", {
      name: `Lead AI: ${models[0].identifier}`,
      exact: true,
    }),
  ).toBeChecked();
  await expect(
    page.getByLabel("Specialist allocation", { exact: true }),
  ).toHaveValue("manual");
  await expect(
    page.getByRole("radio", {
      name: `Business Analyst model: ${models[1].identifier}`,
      exact: true,
    }),
  ).toBeChecked();
  const saved = await (await request.get(`/api/project-drafts/${id}`)).json();
  expect(saved.data.form.worker_model_ids).toEqual([models[1].id]);
  expect(saved.lead_status.allowed).toBe(false);
  const submitted = await request.post(`/api/project-drafts/${id}/submit`, {
    headers,
    data: { request_id: crypto.randomUUID(), version: saved.version },
  });
  expect(submitted.status()).toBe(200);
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/project-drafts/${id}`)).json()).workflow
          .status,
    )
    .toBe("waiting_for_free_provider");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page
    .getByRole("button", { name: "Choose an alternate Lead AI", exact: true })
    .click();
  await expect(
    page.getByRole("radio", {
      name: `Lead AI: ${models[0].identifier}`,
      exact: true,
    }),
  ).toBeChecked();
  await page.screenshot({ path: "../../data/catalog-fixture-mobile.png" });
  const layout = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
    overflow: [...document.querySelectorAll(".project-wizard *")]
      .filter(
        (element) => element.getBoundingClientRect().right > window.innerWidth,
      )
      .map((element) => ({
        tag: element.tagName,
        class: element.className,
        width: element.getBoundingClientRect().width,
      })),
  }));
  expect(layout.width, JSON.stringify(layout)).toBeLessThanOrEqual(
    layout.viewport,
  );
  const state = await (await request.get("/api/state")).json();
  expect(
    state.runs.filter((r: { model_id: string }) =>
      models.some((m: { id: string }) => m.id === r.model_id),
    ),
  ).toHaveLength(0);
});

test("registered blocked model saves as a project default and an exact task preference", async ({
  page,
}) => {
  const fixture = JSON.parse(
    readFileSync("../../data/phase5-browser-state.json", "utf8"),
  );
  const request = page.context().request;
  const headers = { Origin: "http://localhost:3001" };
  await loginAccount(
    request,
    {
      email: "phase5-owner@fixture.test",
      password: "phase5-fixture-owner-password",
    },
    "http://localhost:3001",
  );
  expect(
    (
      await request.post(
        `/api/providers/${fixture.catalog_providers[0].id}/discover`,
        { headers, data: {} },
      )
    ).status(),
  ).toBe(200);
  const catalog = await (await request.get("/api/model-catalog")).json();
  const model = catalog.models.find(
    (m: { provider_id: string }) =>
      m.provider_id === fixture.catalog_providers[0].id,
  );
  const state = await (await request.get("/api/state")).json();
  const intake = await request.post("/api/requirements", {
    headers,
    data: {
      client_id: state.clients[0].id,
      title: "Catalog task contract",
      text: "Explicit deterministic planning contract for saved model preferences and authorization gates.",
      mode: "mock",
      budget_micro: 5000000,
    },
  });
  expect(intake.status()).toBe(201);
  const requirement = await intake.json();
  let proposal: {
    id: string;
    version: number;
    content_hash: string;
    content: { recommendation: string };
  };
  await expect
    .poll(async () => {
      const current = await (await request.get("/api/state")).json();
      proposal = current.proposals.find(
        (p: { requirement_id: string }) => p.requirement_id === requirement.id,
      );
      return !!proposal;
    })
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
  await page.goto("/?view=models");
  await page
    .getByRole("button", { name: "Routing policy", exact: true })
    .click();
  const policy = page.locator("details").filter({
    has: page
      .locator("summary")
      .filter({ hasText: `${project.name} · project model restrictions` }),
  });
  await policy.locator(":scope > summary").click();
  await policy
    .getByLabel("Preferred model", { exact: true })
    .selectOption(model.id);
  await policy
    .getByRole("button", { name: "Save model policy", exact: true })
    .click();
  await expect
    .poll(async () => {
      const current = await (await request.get("/api/state")).json();
      return current.model_policies.find(
        (p: { scope: string }) => p.scope === `project:${project.id}`,
      )?.preferred_model_id;
    })
    .toBe(model.id);
  await page.goto("/?view=allocation");
  await page
    .getByLabel("Staffing project", { exact: true })
    .selectOption(project.id);
  await expect(
    page.getByRole("heading", { name: "Team proposal · v1", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Task model selection mode", { exact: true })
    .selectOption("hybrid");
  await page
    .getByRole("button", { name: "Save workforce changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Team proposal · v2", exact: true }),
  ).toBeVisible();
  const plan = await (
    await request.get(`/api/projects/${project.id}/staffing`)
  ).json();
  const key = plan.content.tasks[0].key;
  const card = page
    .locator("details.allocation-task")
    .filter({ has: page.getByLabel(`Model ${key}`, { exact: true }) });
  await card.locator(":scope > summary").click();
  await page.getByLabel(`Model ${key}`, { exact: true }).selectOption(model.id);
  await page
    .getByRole("button", { name: "Save workforce changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Team proposal · v3", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Team proposal · v3", exact: true }),
  ).toBeVisible();
  await card.locator(":scope > summary").click();
  await expect(page.getByLabel(`Model ${key}`, { exact: true })).toHaveValue(
    model.id,
  );
  await expect(
    card.getByText("WAITING_FOR_FREE_PROVIDER", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve exact workforce", exact: true })
    .click();
  await expect
    .poll(async () => {
      const current = await (
        await request.get(`/api/projects/${project.id}/staffing`)
      ).json();
      return current.tasks.find(
        (t: { payload: { plan_key: string } }) => t.payload.plan_key === key,
      )?.status;
    })
    .toBe("waiting_for_free_provider");
  const persisted = await (
    await request.get(`/api/projects/${project.id}/staffing`)
  ).json();
  expect(persisted.content.tasks[0].preferred_model_id).toBe(model.id);
  expect(persisted.budget.spent_micro).toBe(0);
  expect(persisted.budget.reserved_micro).toBe(0);
});
