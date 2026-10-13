import { testOrigin } from "./support/environment";
import { fixtureSetting as setting } from "./support/environment";
import { test, expect } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page) {
  const response = await page.context().request.post("/api/auth/login", {
    data: {
      email: setting("OWNER_EMAIL"),
      password: setting("OWNER_PASSWORD"),
    },
    headers: { Origin: testOrigin },
  });
  expect(response.status()).toBe(200);
}

test("premium conversation persists uploads, streams real status and renders fixture evidence", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/?view=chat");
  await expect(
    page.getByRole("heading", { name: "Your autonomous AI company." }),
  ).toBeVisible();
  expect(
    await page
      .locator("body")
      .evaluate((element) => getComputedStyle(element).backgroundColor),
  ).toBe("rgb(11, 15, 23)");
  await page.screenshot({
    path: "../../artifacts/premium-chat-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Collapse sidebar", exact: true })
    .click();
  await expect(page.locator(".shell")).toHaveClass(/sidebar-collapsed/);
  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("textbox", { name: "Search company" }),
  ).toBeFocused();
  await page
    .getByRole("button", { name: "Expand sidebar", exact: true })
    .click();
  await page.getByRole("button", { name: "Use light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Use dark theme" }).click();
  await page
    .getByLabel("Conversation provider mode", { exact: true })
    .selectOption("mock");
  await page
    .getByLabel("Attach project document", { exact: true })
    .setInputFiles({
      name: "ui-notes.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "# Browser context\nRetain project requirements across restarts.",
      ),
    });
  await expect(page.locator(".composer-attachments")).toContainText(
    "ui-notes.md",
  );
  const question = `Browser conversation fixture ${Date.now()}: review the attached requirements.`;
  await page
    .getByLabel("Message your AI company", { exact: true })
    .fill(question);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".markdown")).toContainText(
    "Local fixture · no live AI call",
    { timeout: 20000 },
  );
  await expect(page.locator(".markdown table")).toContainText("Persisted");
  await expect(page.locator(".markdown pre")).toContainText(
    "no generated code executed",
  );
  await expect(page.locator(".composer-footnote")).toContainText(
    "Events: Connected",
    { timeout: 10000 },
  );
  const savedURL = page.url();
  expect(savedURL).toContain("conversation=");
  await page.reload();
  await expect(page.locator(".human-message")).toContainText(question);
  await page
    .locator(".human-message")
    .getByRole("button", { name: "ui-notes.md", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Attached document" }),
  ).toContainText("Retain project requirements");
  await expect(
    page.getByRole("button", { name: "Close document" }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Close document" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Close document" }).click();
  await expect(
    page
      .locator(".human-message")
      .getByRole("button", { name: "ui-notes.md", exact: true }),
  ).toBeFocused();
  await page.locator(".execution-details summary").click();
  await expect(page.locator(".run-evidence")).toContainText("mock_no_charge");
  await page.screenshot({
    path: "../../artifacts/premium-conversation.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Conversations", exact: true })
    .click();
  await page.getByLabel("Search conversations").fill(question.slice(0, 40));
  await expect(page.locator(".history-list > button")).toHaveCount(1);
  await page.locator(".history-list > button").click();
  await expect(page.locator(".human-message")).toContainText(question);
});

test("live conversation waits honestly and cancellation persists after reload", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/?view=chat");
  const state = await (await page.context().request.get("/api/state")).json();
  test.skip(
    state.runtime.providers.some(
      (provider: { mode: string; status: string }) =>
        provider.mode === "live" && provider.status === "configured_unverified",
    ),
    "This missing-provider check is only valid without a configured live provider.",
  );
  await page
    .getByLabel("Message your AI company")
    .fill(
      "Review architecture with a real AI model; wait if no provider is configured.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByText("Waiting for an eligible free AI model", { exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.locator(".markdown")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Stop response", exact: true })
    .click();
  await expect(
    page.getByText("Response stopped", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Response stopped", { exact: true }),
  ).toBeVisible();
  const id = new URL(page.url()).searchParams.get("conversation");
  const record = await (
    await page.context().request.get(`/api/conversations/${id}`)
  ).json();
  expect(record.turns[0].runs).toHaveLength(0);
  expect(record.turns[0].workflow.status).toBe("cancelled");
});

test("mobile chat and navigation stay usable without overflow", async ({
  page,
}) => {
  await signIn(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=chat");
  await expect(page.getByLabel("Message your AI company")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../artifacts/premium-chat-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.locator(".sidebar")).toBeInViewport();
  await page
    .getByRole("button", { name: "Conversations", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Conversations", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".shell")).not.toHaveClass(/menu-open/);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(page.getByLabel("Message your AI company")).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/premium-chat-laptop.png",
    fullPage: true,
  });
});

test("chat consultation opens exact approval and creates its persistent project", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/?view=chat");
  await page
    .getByLabel("Conversation provider mode", { exact: true })
    .selectOption("mock");
  await page.getByRole("button", { name: "Plan a new application" }).click();
  const brief = `Chat consultation fixture ${Date.now()}: plan an application with architecture, cloud costs, security and approval before implementation.`;
  await page.getByLabel("Message your AI company").fill(brief);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".consultation-result")).toContainText(
    "awaiting approval",
    { timeout: 30000 },
  );
  const conversationURL = page.url();
  const id = new URL(conversationURL).searchParams.get("conversation");
  const saved = await (
    await page.context().request.get(`/api/conversations/${id}`)
  ).json();
  const consultation = saved.turns[0].consultation;
  expect(consultation.proposals).toHaveLength(1);
  let state = await (await page.context().request.get("/api/state")).json();
  expect(
    state.projects.filter(
      (project: { proposal_id: string }) =>
        project.proposal_id === consultation.proposals[0].id,
    ),
  ).toHaveLength(0);
  await page
    .getByRole("button", { name: "Review consultation & proposal" })
    .click();
  await expect(page).toHaveURL(
    new RegExp(`requirement=${consultation.requirement.id}`),
  );
  await expect(
    page.getByRole("heading", { name: "Solution proposal · v1", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Solution proposal · v1", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve selected solution", exact: true })
    .click();
  await expect(page).toHaveURL(/view=projects&project=/);
  const projectId = new URL(page.url()).searchParams.get("project");
  state = await (await page.context().request.get("/api/state")).json();
  const project = state.projects.find(
    (row: { id: string }) => row.id === projectId,
  );
  expect(project.proposal_id).toBe(consultation.proposals[0].id);
  expect(
    state.tasks.filter(
      (task: { project_id: string }) => task.project_id === project.id,
    ),
  ).toHaveLength(4);
  await expect(
    page.getByRole("heading", { name: project.name, exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/premium-approved-project.png",
    fullPage: true,
  });
  await page.goto(conversationURL);
  await expect(page.locator(".consultation-result")).toContainText("approved", {
    timeout: 10000,
  });
});
