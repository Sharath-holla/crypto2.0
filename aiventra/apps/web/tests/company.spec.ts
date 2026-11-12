import { testOrigin } from "./support/environment";
import { fixtureSetting as setting } from "./support/environment";
import { test, expect } from "@playwright/test";

test("owner consults, approves and inspects a real persistent project", async ({
  page,
}) => {
  const login = await page.context().request.post("/api/auth/login", {
    data: {
      email: setting("OWNER_EMAIL"),
      password: setting("OWNER_PASSWORD"),
    },
    headers: { Origin: testOrigin },
  });
  expect(login.status()).toBe(200);
  await page.goto("/?view=overview");
  await expect(
    page.getByRole("heading", { name: "Company overview", exact: true }),
  ).toBeVisible();
  const state = await page.context().request.get("/api/state");
  expect(state.headers()["x-request-id"]).toBeTruthy();
  expect((await state.json()).runtime.worker.status).toBe("ready");
  await page
    .getByRole("button", { name: "Models & providers", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Connection readiness", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Company overview", exact: true })
    .click();
  await page.screenshot({
    path: "../../artifacts/dashboard.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Client requirements", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Submit requirement", exact: true })
    .click();
  const title = `Browser fixture migration ${Date.now()}`;
  await page.getByLabel("Requirement title", { exact: true }).fill(title);
  await page.getByLabel("Execution mode", { exact: true }).selectOption("mock");
  await page
    .getByLabel("Client requirement", { exact: true })
    .fill(
      "Compare moving our Google Cloud CPU workloads to Lightning AI. Assess compatibility, costs and rollback before any changes.",
    );
  await page
    .getByRole("button", { name: "Begin consultation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Solution proposal · v1", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("Local fixture", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Approve selected solution", exact: true })
    .click();
  await expect(page).toHaveURL(/view=projects&project=/);
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Write architecture assessment/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Open QA & review stage", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Independent QA & review", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "No engineering task has produced independent QA evidence yet.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dependencies", exact: true }).click();
  await expect(page.locator(".dependency-list > div")).toHaveCount(3);
  await page.getByRole("button", { name: "Engineering", exact: true }).click();
  await expect(
    page.getByLabel("Reviewer diversity", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Reviewer diversity", { exact: true })
    .selectOption("require_provider");
  await page
    .getByLabel("Independent reviews", { exact: true })
    .selectOption("2");
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await page
    .getByRole("button", { name: "Assign specialist", exact: true })
    .click();
  await page
    .getByLabel("Specialist", { exact: true })
    .selectOption({ label: "HR Manager" });
  await page.getByLabel("Provider mode", { exact: true }).selectOption("mock");
  const specialistObjective = `Assess project workforce readiness ${Date.now()}`;
  await page
    .getByLabel("Task objective", { exact: true })
    .fill(specialistObjective);
  await page
    .getByLabel("Acceptance criteria (one per line)", { exact: true })
    .fill("Produce a persisted workforce assessment artifact");
  await page
    .getByRole("button", { name: "Queue specialist task", exact: true })
    .click();
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(specialistObjective) }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Artifacts", exact: true }).click();
  const artifact = page.locator("summary").filter({
    hasText: "Write architecture assessment and unresolved assumptions",
  });
  await expect(artifact).toBeVisible({ timeout: 30000 });
  await artifact.click();
  await expect(
    page
      .locator("details[open] pre")
      .filter({ hasText: "Fixture artifact for local workflow testing" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Security & audit", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Verify hash chain", exact: true })
    .click();
  await expect(
    page.locator("pre").filter({ hasText: '"valid": true' }),
  ).toBeVisible();
  await page.getByRole("button", { name: "AI workforce", exact: true }).click();
  await page.getByLabel("Find employee", { exact: true }).fill("CEO");
  await page.getByRole("button", { name: /CEO.*Executive Office/ }).click();
  await expect(
    page.getByRole("heading", { name: "CEO", exact: true, level: 2 }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Close employee", exact: true })
    .click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect((await page.context().request.get("/api/state")).status()).toBe(401);
});

test("mobile owner dashboard fits the viewport", async ({ page }) => {
  const login = await page.context().request.post("/api/auth/login", {
    data: {
      email: setting("OWNER_EMAIL"),
      password: setting("OWNER_PASSWORD"),
    },
    headers: { Origin: testOrigin },
  });
  expect(login.status()).toBe(200);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=overview");
  await expect(
    page.getByRole("heading", { name: "Company overview", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../artifacts/dashboard-mobile.png",
    fullPage: true,
  });
});

test("authentication and CSRF remain enforced by the web proxy", async ({
  request,
}) => {
  const unauth = await request.get("/api/state");
  expect(unauth.status()).toBe(401);
  const rejected = await request.post("/api/auth/login", {
    data: { email: "invalid", password: "invalid" },
    headers: { Origin: "https://attacker.example" },
  });
  expect(rejected.status()).toBe(403);
});
