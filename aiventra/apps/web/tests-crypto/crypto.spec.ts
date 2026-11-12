import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request, context }) => {
  const login = await request.post("/api/auth/login", {
    data: {
      email: "crypto-owner@fixture.test",
      password: "synthetic-crypto-browser-password",
    },
    headers: { Origin: "http://localhost:3004" },
  });
  expect(login.status()).toBe(200);
  await context.addCookies((await request.storageState()).cookies);
});

test("canonical read-only views, exact approval and detached health completion", async ({
  page,
  context,
}) => {
  await page.goto("/?view=crypto");
  const workspace = page.getByTestId("crypto-workspace");
  await expect(
    workspace.getByText("DEMO_FIXTURE_STATE", { exact: true }),
  ).toBeVisible();
  await expect(workspace.getByText("August · LOCKED_UNUSED")).toBeVisible();
  const project = await context.request.get("/api/crypto/project");
  const snapshot = (await project.json()).snapshot;
  expect(snapshot.identity.specs_expected).toBe(48);
  expect(snapshot.identity.folds_expected).toBe(16);
  expect(snapshot.identity.prospective_holdout_used).toBe(false);
  expect(snapshot.identity.prospective_holdout_evaluation_authorized).toBe(
    false,
  );
  expect(snapshot.identity.july_2026_used).toBe(false);
  expect(snapshot.models).toHaveLength(48);
  expect(
    snapshot.models.every((row: { metrics: unknown }) => row.metrics == null),
  ).toBe(true);
  for (const name of [
    "Scientific Identity",
    "Lineage",
    "Data",
    "Folds",
    "Preparation",
    "Training",
    "Models",
    "Metrics",
    "Artifacts",
    "Logs",
    "Recovery",
    "Resources",
    "Settings",
  ]) {
    await workspace
      .getByRole("navigation", { name: "Crypto navigation" })
      .getByRole("button", { name, exact: true })
      .click();
    await expect(workspace.locator(".panel").first()).toBeVisible();
  }
  await workspace
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await page.screenshot({
    path: "../../artifacts/crypto-overview-desktop.png",
    fullPage: true,
  });
  await workspace
    .getByRole("button", { name: "Register existing Crypto project" })
    .click();
  await expect(
    workspace.getByRole("button", { name: "Register existing Crypto project" }),
  ).toHaveCount(0);
  await workspace.getByRole("button", { name: "Jobs", exact: true }).click();
  // Explicit small health-only contract; never relax a scientific workload's gate.
  await workspace.getByLabel("Crypto minimum free RAM").fill("0.1");
  await workspace
    .getByRole("button", { name: "Preview operation (does not execute)" })
    .click();
  await expect(
    workspace.getByRole("button", { name: "Approve exact operation" }),
  ).toBeDisabled();
  let jobs = await (await context.request.get("/api/crypto/jobs")).json();
  expect(jobs).toHaveLength(1);
  expect(jobs[0].record.status).toBe("PENDING_APPROVAL");
  expect(jobs[0].runtime).toBeNull();
  const id = jobs[0].record.id;
  await workspace.getByRole("checkbox").check();
  await workspace
    .getByRole("button", { name: "Approve exact operation" })
    .click();
  await expect(
    workspace.getByRole("button", { name: "Inspect job evidence" }),
  ).toBeVisible();
  await page.close(); // The browser is not the worker's lifetime owner.
  await expect
    .poll(
      async () => {
        jobs = await (await context.request.get("/api/crypto/jobs")).json();
        return jobs.find(
          (item: { record: { id: string } }) => item.record.id === id,
        )?.runtime?.state;
      },
      { timeout: 60000 },
    )
    .toBe("COMPLETED");
  expect(jobs[0].runtime.completion_verified).toBe(true);
  const logs = await context.request.get(`/api/crypto/jobs/${id}/logs`);
  expect(logs.status()).toBe(200);
  expect((await logs.json()).read_only).toBe(true);
  const reopened = await context.newPage();
  await reopened.goto("/?view=crypto");
  await reopened
    .getByRole("navigation", { name: "Crypto navigation" })
    .getByRole("button", { name: "Jobs", exact: true })
    .click();
  await expect(
    reopened
      .getByTestId("crypto-workspace")
      .getByText("COMPLETED", { exact: true })
      .first(),
  ).toBeVisible();
});

test("scientific execution stays blocked and unsafe paths or shell fields are rejected", async ({
  request,
}) => {
  await request.post("/api/crypto/register", {
    data: {},
    headers: { Origin: "http://localhost:3004" },
  });
  const payload = {
    request_id: crypto.randomUUID(),
    job_type: "CRYPTO_FOLD_TRAIN",
    spec_id: "architecture-G0-A6-60m-raw",
    maximum_runtime_seconds: 60,
    deadline_utc: Math.floor(Date.now() / 1000) + 180,
    cost_ceiling: "0",
    cost_currency: "INR",
  };
  const response = await request.post("/api/crypto/jobs/preview", {
    data: payload,
    headers: { Origin: "http://localhost:3004" },
  });
  expect(response.status()).toBe(200);
  const row = await response.json();
  expect(row.data.scope.execution_blockers.length).toBeGreaterThan(0);
  expect(
    (
      await request.post(`/api/crypto/jobs/${row.id}/approve`, {
        data: { version: row.version, scope_hash: row.data.scope.scope_hash },
        headers: { Origin: "http://localhost:3004" },
      })
    ).status(),
  ).toBe(409);
  expect(
    (
      await request.post("/api/crypto/jobs/preview", {
        data: { ...payload, request_id: crypto.randomUUID(), command: "shell" },
        headers: { Origin: "http://localhost:3004" },
      })
    ).status(),
  ).toBe(422);
  expect(
    (
      await request.get("/api/crypto/document?category=reports&path=../../.env")
    ).status(),
  ).not.toBe(200);
  expect(
    (await request.get("/api/crypto/artifacts?category=gold&path=.")).status(),
  ).not.toBe(200);
  expect(
    (
      await request.post("/api/crypto/holdout/unlock", {
        data: {},
        headers: { Origin: "http://localhost:3004" },
      })
    ).status(),
  ).toBe(404);
});

test("mobile layout keeps evidence readable without page overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=crypto");
  await expect(
    page
      .getByTestId("crypto-workspace")
      .getByText("DEMO_FIXTURE_STATE", { exact: true }),
  ).toBeVisible();
  for (const name of [
    "Overview",
    "Models",
    "Folds",
    "Jobs",
    "Scientific Identity",
  ]) {
    await page
      .getByRole("navigation", { name: "Crypto navigation" })
      .getByRole("button", { name, exact: true })
      .click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: "../../artifacts/crypto-mobile.png",
    fullPage: true,
  });
});
