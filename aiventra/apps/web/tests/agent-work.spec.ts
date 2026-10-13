import { testOrigin } from "./support/environment";
import { fixtureSetting as setting } from "./support/environment";
import { test, expect, type Page } from "@playwright/test";
import type { State } from "../src/lib/types";

const headers = { Origin: testOrigin };
async function signIn(page: Page) {
  const login = await page.context().request.post("/api/auth/login", {
    data: {
      email: setting("OWNER_EMAIL"),
      password: setting("OWNER_PASSWORD"),
    },
    headers,
  });
  expect(login.status()).toBe(200);
}
async function state(page: Page): Promise<State> {
  return (await page.context().request.get("/api/state")).json();
}

test("provider UI encrypts a key without readback and records an actual failed local catalog check", async ({
  page,
}) => {
  await signIn(page);
  const name = `Browser vault contract ${Date.now()}`;
  const registration = await page.context().request.post("/api/providers", {
    data: {
      name,
      kind: "openai",
      base_url: "https://api.openai.com/v1",
      credential_env: "BROWSER_VAULT_TEST_API_KEY",
    },
    headers,
  });
  expect(registration.status()).toBe(201);
  const provider = await registration.json();
  const key = "browser-controlled-opaque-credential";
  const localRegistration = await page
    .context()
    .request.post("/api/providers", {
      data: {
        name: `Unreachable local catalog ${Date.now()}`,
        kind: "ollama",
        base_url: "http://127.0.0.1:9",
        credential_env: "",
      },
      headers,
    });
  expect(localRegistration.status()).toBe(201);
  const local = await localRegistration.json();
  try {
    await page.goto("/?view=models");
    await page
      .getByRole("button", { name: "Provider connections", exact: true })
      .click();
    const card = page
      .locator(".provider-card")
      .filter({ has: page.getByRole("heading", { name, exact: true }) });
    await card.getByLabel(`${name} API key`, { exact: true }).fill(key);
    await card
      .getByRole("button", { name: "Save encrypted key", exact: true })
      .click();
    await expect(
      card.getByText("Credential source: vault.", { exact: true }),
    ).toBeVisible();
    await expect(
      card.getByLabel(`${name} API key`, { exact: true }),
    ).toHaveValue("");
    expect(JSON.stringify(await state(page))).not.toContain(key);
    await expect(
      card.getByText("inference unverified", { exact: true }),
    ).toBeVisible();
    await card
      .getByRole("button", { name: "Remove stored key", exact: true })
      .click();
    await expect(
      card.getByText("Credential source: none.", { exact: true }),
    ).toBeVisible();
    const localCard = page.locator(".provider-card").filter({
      has: page.getByRole("heading", { name: local.name, exact: true }),
    });
    await localCard
      .getByRole("button", {
        name: "Test connection & discover models",
        exact: true,
      })
      .click();
    await expect(
      localCard.getByText("catalog_failed", { exact: true }),
    ).toBeVisible();
    await expect(localCard.getByText(/catalog_network_failure/)).toBeVisible();
    await page.screenshot({
      path: "../../artifacts/provider-controls.png",
      fullPage: true,
    });
  } finally {
    await page
      .context()
      .request.post(`/api/providers/${provider.id}/credentials/revoke`, {
        data: {},
        headers,
      });
    for (const id of [provider.id, local.id])
      await page.context().request.patch(`/api/providers/${id}`, {
        data: { enabled: false },
        headers,
      });
  }
});

test("agent message and meeting UI produce persistent fixture evidence and runtime states", async ({
  page,
}) => {
  await signIn(page);
  const initial = await state(page);
  const title = `Agent UI workflow ${Date.now()}`;
  const intake = await page.context().request.post("/api/requirements", {
    data: {
      client_id: initial.clients[0].id,
      title,
      text: "Assess a project task application and produce acceptance evidence before implementation",
      mode: "mock",
    },
    headers,
  });
  expect(intake.status()).toBe(201);
  const requirement = await intake.json();
  let proposal: State["proposals"][number] | undefined;
  await expect
    .poll(async () => {
      proposal = (await state(page)).proposals.find(
        (p) => p.requirement_id === requirement.id,
      );
      return Boolean(proposal);
    })
    .toBe(true);
  const approval = await page
    .context()
    .request.post(`/api/proposals/${proposal!.id}/approve`, {
      data: {
        version: proposal!.version,
        content_hash: proposal!.content_hash,
        selection: proposal!.content.recommendation,
      },
      headers,
    });
  expect(approval.status()).toBe(200);
  const project = await approval.json();
  expect(typeof project.id).toBe("string");
  expect((await state(page)).projects.some((p) => p.id === project.id)).toBe(
    true,
  );
  await page.goto("/?view=meetings");
  await expect(
    page.getByRole("heading", { name: "Direct agent work", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Approved project", { exact: true })
    .selectOption(project.id);
  await page
    .getByLabel("Agent work provider mode", { exact: true })
    .selectOption("mock");
  const sender = initial.agents.find((a) => a.role === "CTO")!;
  const recipient = initial.agents.find((a) => a.role === "Business Analyst")!;
  await page
    .getByLabel("Sender agent", { exact: true })
    .selectOption(sender.id);
  await page
    .getByLabel("Recipient agent", { exact: true })
    .selectOption(recipient.id);
  await page
    .getByLabel("Agent message objective", { exact: true })
    .fill("Document missing acceptance evidence for the scoped project");
  await page
    .getByRole("button", { name: "Queue agent message", exact: true })
    .click();
  await expect
    .poll(async () => {
      const snapshot = await state(page);
      const work = snapshot.agent_work.find(
        (w) => w.project_id === project.id && w.kind === "message",
      );
      return work
        ? snapshot.workflows.find((w) => w.id === work.workflow_id)?.status
        : "missing";
    })
    .toBe("completed");
  await page.reload();
  const execution = page
    .locator("section")
    .filter({
      has: page.getByRole("heading", {
        name: "Agent work execution",
        exact: true,
      }),
    })
    .locator("details")
    .filter({ hasText: title })
    .first();
  await execution.locator("summary").click();
  await expect(execution.getByText("completed", { exact: true })).toBeVisible();
  await expect(
    execution.getByText(/Fixture artifact for local workflow testing/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Convene a meeting", exact: true })
    .click();
  await page
    .getByLabel("Approved project", { exact: true })
    .selectOption(project.id);
  await page
    .getByLabel("Agent work provider mode", { exact: true })
    .selectOption("mock");
  await page.getByLabel(sender.name, { exact: true }).check();
  await page.getByLabel(recipient.name, { exact: true }).check();
  await page
    .getByLabel("Meeting agenda", { exact: true })
    .fill("Independently assess risks and unresolved acceptance evidence");
  await page
    .getByRole("button", { name: "Start bounded meeting", exact: true })
    .click();
  await expect
    .poll(async () => {
      const snapshot = await state(page);
      const work = snapshot.agent_work.find(
        (w) => w.project_id === project.id && w.kind === "meeting",
      );
      return work
        ? snapshot.workflows.find((w) => w.id === work.workflow_id)?.status
        : "missing";
    })
    .toBe("completed");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Agent work execution", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/agent-work-controls.png",
    fullPage: false,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Direct agent work", exact: true }),
  ).toBeVisible();
  await expect
    .poll(async () =>
      page
        .locator(".sidebar")
        .evaluate((element) => element.getBoundingClientRect().right),
    )
    .toBeLessThanOrEqual(1);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
  await page.screenshot({
    path: "../../artifacts/agent-work-mobile.png",
    fullPage: false,
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/?view=workforce");
  await page.getByLabel("Find employee", { exact: true }).fill(recipient.name);
  await page.locator(".agent-card").first().click();
  await expect(
    page.getByText("Recorded execution transitions", { exact: true }),
  ).toBeVisible();
  // An older active provider wait can correctly outrank this completed job in
  // the employee's current runtime. Verify completion in its persisted history.
  await page
    .getByText("Recorded execution transitions", { exact: true })
    .click();
  await expect(
    page.getByText("COMPLETED", { exact: true }).first(),
  ).toBeVisible();
});
