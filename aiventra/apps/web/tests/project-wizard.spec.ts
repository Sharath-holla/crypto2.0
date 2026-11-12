import { testOrigin } from "./support/environment";
import { test, expect, type Page } from "@playwright/test";
import { loginOwner } from "./support/login";
async function login(page: Page) {
  await loginOwner(page.context().request);
}
async function describe(page: Page, suffix: string) {
  await page.goto("/?view=new-project");
  await page
    .getByLabel("Project name", { exact: true })
    .fill(`Wizard browser fixture ${suffix} ${Date.now()}`);
  await page
    .getByLabel("Project requirements", { exact: true })
    .fill(
      "Build an accessible tracker with persistent records, independent tests and explicit owner approvals.",
    );
  await expect(
    page.getByRole("status").filter({ hasText: "Saved · version" }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.get("draft")).toBeTruthy();
}

test("simple home has seven primary destinations including Crypto and retains advanced tools", async ({
  page,
}) => {
  await login(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "What would you like to build?" }),
  ).toBeVisible();
  await expect(page.locator(".primary-navigation button")).toHaveCount(7);
  await expect(
    page
      .locator(".primary-navigation")
      .getByRole("button", { name: "Crypto 2.0", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Models & providers", exact: true }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "Advanced", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Models & providers", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Advanced", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
  await page
    .getByLabel("Describe your project", { exact: true })
    .fill("A customer portal with saved requirements and explicit approvals.");
  await page
    .getByRole("button", { name: "Start project", exact: true })
    .click();
  await expect(
    page.getByLabel("Project requirements", { exact: true }),
  ).toHaveValue(
    "A customer portal with saved requirements and explicit approvals.",
  );
});

test("wizard persists autosaved step and uploads, and rejects stale browser edits", async ({
  page,
}) => {
  await login(page);
  await describe(page, "saved draft");
  await page
    .getByLabel("Upload project requirements", { exact: true })
    .setInputFiles({
      name: "browser-requirements.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "# Acceptance\nRecords survive restart and uploads remain versioned.",
      ),
    });
  await expect(
    page.getByText(/browser-requirements.md · parsed and saved/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Choose your Lead AI", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Saved · version" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Choose your Lead AI", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("group", { name: "Lead AI", exact: true })
      .getByRole("radio", { checked: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText(/cannot currently run under zero-cost mode/),
  ).toBeVisible();
  const id = new URL(page.url()).searchParams.get("draft");
  const record = await (
    await page.context().request.get(`/api/project-drafts/${id}`)
  ).json();
  const changed = await page
    .context()
    .request.patch(`/api/project-drafts/${id}`, {
      headers: { Origin: testOrigin },
      data: {
        request_id: crypto.randomUUID(),
        version: record.version,
        form: {
          ...record.data.form,
          title: "Updated from another browser fixture",
        },
      },
    });
  expect(changed.status()).toBe(200);
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page
    .getByLabel("Project name", { exact: true })
    .fill("This stale edit must never replace the other browser");
  await expect(page.locator('.project-wizard [role="alert"]')).toContainText(
    "Draft changed",
  );
  await page
    .getByRole("button", { name: "Reload saved draft", exact: true })
    .click();
  await page.getByRole("button", { name: "1 Describe", exact: true }).click();
  await expect(page.getByLabel("Project name", { exact: true })).toHaveValue(
    "Updated from another browser fixture",
  );
});

test("unavailable favorite submits a real waiting workflow without model calls", async ({
  page,
}) => {
  await login(page);
  await describe(page, "zero cost wait");
  await page.getByRole("button", { name: "3 Review", exact: true }).click();
  await page
    .getByRole("button", { name: "Submit requirements", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Your requirements are saved",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("waiting_for_free_provider", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
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
  await expect(
    page.getByRole("heading", {
      name: "Model assignments & execution evidence",
      exact: true,
    }),
  ).toBeVisible();
  const evidence = await (
    await page
      .context()
      .request.get(`/api/project-drafts/${id}/execution-evidence`)
  ).json();
  expect(evidence.selection_history).toHaveLength(1);
  expect(evidence.workflows[0].runs).toHaveLength(0);
  expect(evidence.workflows[0].status).toBe("waiting_for_free_provider");
  await page
    .getByRole("button", { name: "Refresh execution evidence", exact: true })
    .click();
  await page
    .locator("summary")
    .filter({ hasText: "waiting for free provider" })
    .first()
    .click();
  await expect(
    page.getByText(
      "An eligible AI model is required to continue. Configure an approved model and resume.",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Verify and resume", exact: true })
    .click();
  await expect(page.locator('.project-wizard [role="alert"]')).toContainText(
    "No eligible verified local model",
  );
  await page.reload();
  await expect(
    page.getByText("waiting_for_free_provider", { exact: true }),
  ).toBeVisible();
});

test("wizard replaces and removes saved documents with provenance after reload", async ({
  page,
}) => {
  await login(page);
  await describe(page, "document lifecycle");
  await page.getByLabel("Project requirements", { exact: true }).fill("");
  await expect(
    page.getByRole("status").filter({ hasText: "Saved · version" }),
  ).toBeVisible();
  const uploader = page.getByLabel("Upload project requirements", {
    exact: true,
  });
  await uploader.setInputFiles({
    name: "original.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "Original document requirements with persistent evidence.",
    ),
  });
  await expect(
    page.getByLabel("Project requirements", { exact: true }),
  ).toHaveValue("Original document requirements with persistent evidence.");
  const replacement = page.getByLabel("Replace requirement attachment", {
    exact: true,
  });
  const attachmentId = await replacement
    .locator("option")
    .nth(1)
    .getAttribute("value");
  await replacement.selectOption(attachmentId!);
  await uploader.setInputFiles({
    name: "replacement.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "Replacement document requirements with independent tests.",
    ),
  });
  await expect(
    page.getByLabel("Project requirements", { exact: true }),
  ).toHaveValue("Replacement document requirements with independent tests.");
  await expect(
    page.getByText(/original.md · parsed and saved/),
  ).not.toBeVisible();
  await page.reload();
  await expect(
    page.getByText(/replacement.md · parsed and saved/),
  ).toBeVisible();
  await page.getByText("Document provenance", { exact: true }).click();
  await expect(page.getByText(/Source SHA-256:/)).toBeVisible();
  await page
    .getByRole("button", { name: "Remove replacement.md", exact: true })
    .click();
  await expect(
    page.getByLabel("Project requirements", { exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByText(/replacement.md · parsed and saved/),
  ).not.toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
});

test("typing during a real attachment request preserves unsaved requirements", async ({
  page,
}) => {
  await login(page);
  await describe(page, "upload edit race");
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/project-drafts/*/attachments", async (route) => {
    await pending;
    await route.continue();
  });
  await page
    .getByLabel("Upload project requirements", { exact: true })
    .setInputFiles({
      name: "slow.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "Additional versioned document evidence for the project.",
      ),
    });
  await expect(
    page.getByRole("status").filter({ hasText: "Saving…" }),
  ).toBeVisible();
  const edited =
    "Owner edits made during upload must persist without being overwritten by the saved server form.";
  await page.getByLabel("Project requirements", { exact: true }).fill(edited);
  release();
  await expect(page.getByText(/slow.md · parsed and saved/)).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Saved · version" }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Project requirements", { exact: true }),
  ).toHaveValue(edited);
  await page.reload();
  await expect(
    page.getByLabel("Project requirements", { exact: true }),
  ).toHaveValue(edited);
});

test("mobile wizard validates uploads and saves a clearly owner-authored proposal", async ({
  page,
}) => {
  await login(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await describe(page, "manual plan");
  await page
    .getByLabel("Upload project requirements", { exact: true })
    .setInputFiles({
      name: "brief.json",
      mimeType: "application/json",
      buffer: Buffer.from("invalid JSON"),
    });
  await expect(page.locator('.project-wizard [role="alert"]')).toContainText(
    "valid JSON",
  );
  await page
    .getByRole("button", { name: "Reload saved draft", exact: true })
    .click();
  await page.getByRole("button", { name: "3 Review", exact: true }).click();
  await page
    .getByLabel("Planning path", { exact: true })
    .selectOption("manual");
  await page
    .getByRole("button", { name: "Submit requirements", exact: true })
    .click();
  await expect(page.getByText("paused", { exact: true })).toBeVisible();
  await expect(
    page.getByLabel("Manual architecture", { exact: true }),
  ).not.toBeVisible();
  await page
    .getByLabel("Scope acceptance criteria", { exact: true })
    .fill("Records persist and owner reviews exact scope");
  await page
    .getByRole("button", { name: "Save reviewed scope version", exact: true })
    .click();
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
  await page
    .getByLabel("Manual architecture", { exact: true })
    .fill(
      "SQLite tracker with scoped API, restricted engineering and independent QA.",
    );
  await page
    .getByLabel("Manual milestones", { exact: true })
    .fill("Build the tracker\nValidate records after restart");
  await page
    .getByLabel("Manual acceptance criteria", { exact: true })
    .fill("Records persist and owner reviews exact scope");
  await page
    .getByRole("button", { name: "Save owner-authored proposal", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Your plan is ready for review",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../artifacts/simple-project-wizard-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("button", {
      name: "Review requirements and approvals",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Owner-authored plan; no AI-generated analysis", {
      exact: true,
    }),
  ).toBeVisible();
});
