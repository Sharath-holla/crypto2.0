import { testOrigin } from "./support/environment";
import { expect, test } from "@playwright/test";
import { loginOwner } from "./support/login";

function textPdf(text: string) {
  const stream = `BT /F1 12 Tf 20 200 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let raw = "%PDF-1.4\n";
  const offsets = objects.map((object, index) => {
    const offset = Buffer.byteLength(raw);
    raw += `${index + 1} 0 obj\n${object}\nendobj\n`;
    return offset;
  });
  const xref = Buffer.byteLength(raw);
  raw += `xref\n0 6\n0000000000 65535 f \n${offsets.map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(raw);
}

test("PDF upload, reprocess, replace and remove use real versioned backend", async ({
  page,
}) => {
  await loginOwner(page.context().request);
  await page.goto("/?view=new-project");
  await page
    .getByLabel("Project name", { exact: true })
    .fill(`PDF browser fixture ${Date.now()}`);
  await expect(
    page.getByRole("status").filter({ hasText: "Saved · version" }),
  ).toBeVisible();
  const upload = page.getByLabel("Upload project requirements", {
    exact: true,
  });
  await upload.setInputFiles({
    name: "requirements.pdf",
    mimeType: "application/pdf",
    buffer: textPdf(
      "PDF requirements persist with source provenance and approval gates.",
    ),
  });
  await expect(
    page.getByText(/requirements.pdf · parsed and saved/),
  ).toContainText("1 pages · version 1");
  await page
    .getByRole("button", { name: "Reprocess requirements.pdf", exact: true })
    .click();
  await expect(
    page.getByText(/requirements.pdf · parsed and saved/),
  ).toContainText("version 2");
  await page.reload();
  await expect(
    page.getByText(/requirements.pdf · parsed and saved/),
  ).toContainText("version 2");
  const id = new URL(page.url()).searchParams.get("draft");
  const draft = await (
    await page.context().request.get(`/api/project-drafts/${id}`)
  ).json();
  expect(draft.data.attachments[0].source_sha256).toMatch(/^[a-f0-9]{64}$/);
  await page
    .getByLabel("Replace requirement attachment")
    .selectOption(draft.data.attachments[0].id);
  await upload.setInputFiles({
    name: "replacement.pdf",
    mimeType: "application/pdf",
    buffer: textPdf(
      "Replacement PDF project requirements retain exact versioned provenance.",
    ),
  });
  await expect(
    page.getByText(/replacement.pdf · parsed and saved/),
  ).toContainText("version 3");
  await expect(
    page.getByText(/requirements.pdf · parsed and saved/),
  ).toHaveCount(0);
  // Leave one PDF source for actual SQLite/Compose restart verification.
  await upload.setInputFiles({
    name: "retained.pdf",
    mimeType: "application/pdf",
    buffer: textPdf(
      "Retained PDF source for actual process restart integrity verification.",
    ),
  });
  await expect(page.getByText(/retained.pdf · parsed and saved/)).toBeVisible();
  await page
    .getByRole("button", { name: "Remove replacement.pdf", exact: true })
    .click();
  await expect(
    page.getByText(/replacement.pdf · parsed and saved/),
  ).toHaveCount(0);
  await page.screenshot({
    path: "../../artifacts/pdf-provenance.png",
    fullPage: true,
  });
});

test("project history loads older saved events without duplicates during new activity", async ({
  page,
}) => {
  test.setTimeout(120000);
  const request = page.context().request;
  await loginOwner(request);
  const state = await (await request.get("/api/state")).json();
  expect(state.projects.length).toBeGreaterThan(0);
  const project = state.projects[0];
  for (let index = 0; index < 24; index++) {
    const result = await request.post("/api/records", {
      headers: { Origin: testOrigin },
      data: {
        kind: "knowledge",
        title: `History browser fixture ${index}`,
        project_id: project.id,
        data: { fixture: true },
      },
    });
    expect(result.status()).toBe(201);
  }
  await page.goto(`/?view=projects&project=${project.id}`);
  await page.getByRole("button", { name: "Timeline", exact: true }).click();
  const events = page
    .getByRole("list", { name: "Project history", exact: true })
    .locator("li");
  await expect(events).toHaveCount(20);
  const initial = await events.evaluateAll((rows) =>
    rows.map((row) => row.getAttribute("data-event-id")),
  );
  const added = await request.post("/api/records", {
    headers: { Origin: testOrigin },
    data: {
      kind: "knowledge",
      title: "Concurrent history browser fixture",
      project_id: project.id,
      data: { fixture: true },
    },
  });
  expect(added.status()).toBe(201);
  await page
    .getByRole("button", { name: "Load older project activity", exact: true })
    .click();
  await expect.poll(async () => events.count()).toBeGreaterThan(20);
  const combined = await events.evaluateAll((rows) =>
    rows.map((row) => row.getAttribute("data-event-id")),
  );
  expect(new Set(combined).size).toBe(combined.length);
  expect(combined.slice(0, 20)).toEqual(initial);
  await page
    .getByRole("button", { name: "Refresh recent activity", exact: true })
    .click();
  await expect(events).toHaveCount(20);
  expect(await events.first().textContent()).toContain("record.created");
});

test("chat loads older persisted cancelled turns and preserves them when new activity arrives", async ({
  page,
}) => {
  test.setTimeout(180000);
  const request = page.context().request;
  await loginOwner(request);
  const state = await (await request.get("/api/state")).json();
  const id = crypto.randomUUID();
  expect(
    (
      await request.post("/api/conversations", {
        headers: { Origin: testOrigin },
        data: { id, client_id: state.clients[0].id, mode: "live" },
      })
    ).status(),
  ).toBe(201);
  async function addTurn(position: number) {
    const current = await (
      await request.get(`/api/conversations/${id}`)
    ).json();
    const response = await request.post(`/api/conversations/${id}/turns`, {
      headers: { Origin: testOrigin },
      data: {
        request_id: crypto.randomUUID(),
        version: current.conversation.version,
        text: `History cancellation fixture turn ${position}`,
        intent: "chat",
      },
    });
    expect(response.status()).toBe(201);
    const turn = await response.json();
    expect(
      (
        await request.post(`/api/conversations/${id}/turns/${turn.id}/cancel`, {
          headers: { Origin: testOrigin },
          data: {},
        })
      ).status(),
    ).toBe(200);
  }
  for (let position = 1; position <= 23; position++) await addTurn(position);
  await page.goto(`/?view=chat&conversation=${id}`);
  await expect(page.locator(".human-message")).toHaveCount(20);
  await page
    .getByRole("button", { name: "Load older chat history", exact: true })
    .click();
  await expect(page.locator(".human-message")).toHaveCount(23);
  await addTurn(24);
  await expect(page.locator(".human-message")).toHaveCount(24);
  await expect(
    page
      .locator(".human-message")
      .getByText("History cancellation fixture turn 1", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".markdown")).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".human-message")).toHaveCount(20);
  await page
    .getByRole("button", { name: "Load older chat history", exact: true })
    .click();
  await expect(page.locator(".human-message")).toHaveCount(24);
});
