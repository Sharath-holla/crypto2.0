import { testOrigin } from "./support/environment";
import { test, expect, type Page } from "@playwright/test";
import { loginOwner } from "./support/login";
import type { State } from "../src/lib/types";

const headers = { Origin: testOrigin };
const state = async (page: Page): Promise<State> =>
  (await page.context().request.get("/api/state")).json();

test("native tools and benchmark UI queue scoped live work, wait without credentials and cancel", async ({
  page,
}) => {
  test.setTimeout(90000);
  await loginOwner(page.context().request);
  let snapshot = await state(page);
  const title = `Native browser contracts ${Date.now()}`;
  const providerResponse = await page.context().request.post("/api/providers", {
    headers,
    data: {
      name: title,
      kind: "openai",
      base_url: "https://api.openai.com/v1",
      credential_env: "NATIVE_BROWSER_UNCONFIGURED_API_KEY",
    },
  });
  expect(providerResponse.status()).toBe(201);
  const provider = await providerResponse.json();
  const modelResponse = await page.context().request.post("/api/models", {
    headers,
    data: {
      provider_id: provider.id,
      identifier: title,
      capabilities: ["structured", "tools", "streaming"],
      context_tokens: 65536,
      quality: 95,
      reliability: 100,
      input_price_micro_per_million: 1000000,
      output_price_micro_per_million: 1000000,
      price_source: "https://example.test/browser-contract",
      sensitivity: "confidential",
    },
  });
  expect(modelResponse.status()).toBe(201);
  const model = await modelResponse.json();
  const queued: string[] = [];
  try {
    await page.goto("/?view=models");
    await page.getByRole("button", { name: "Benchmarks", exact: true }).click();
    await expect(
      page.getByText(
        /Use an exact job override or the employee's selected model preference/,
      ),
    ).toBeVisible();
    await page
      .getByLabel("Benchmark model", { exact: true })
      .selectOption(model.id);
    await page
      .getByRole("button", { name: "Run capped benchmark", exact: true })
      .click();
    await expect
      .poll(async () => {
        snapshot = await state(page);
        const job = snapshot.agent_work.find(
          (w) => w.kind === "benchmark" && w.subject_id === model.id,
        );
        if (job && !queued.includes(job.id)) queued.push(job.id);
        return snapshot.workflows.find((w) => w.id === job?.workflow_id)
          ?.status;
      })
      .toBe("waiting_for_free_provider");
    await page.reload();
    await page.getByRole("button", { name: "Benchmarks", exact: true }).click();
    await expect(
      page.getByText("waiting_for_free_provider", { exact: true }).first(),
    ).toBeVisible();
    await page.screenshot({
      path: "../../artifacts/native-benchmarks.png",
      fullPage: false,
      animations: "disabled",
    });
    let project = snapshot.projects.find((p) => p.status === "active");
    if (!project) {
      const intake = await page.context().request.post("/api/requirements", {
        headers,
        data: {
          client_id: snapshot.clients[0].id,
          title,
          text: "Build a harmless document tracker with explicit acceptance evidence.",
          constraints: {},
          mode: "mock",
          budget_micro: 1000000,
          sensitivity: "internal",
        },
      });
      expect(intake.status()).toBe(201);
      const requirement = await intake.json();
      await expect
        .poll(async () =>
          (await state(page)).proposals.some(
            (p) => p.requirement_id === requirement.id,
          ),
        )
        .toBe(true);
      const proposal = (await state(page)).proposals.find(
        (p) => p.requirement_id === requirement.id,
      )!;
      const approval = await page
        .context()
        .request.post(`/api/proposals/${proposal.id}/approve`, {
          headers,
          data: {
            version: proposal.version,
            content_hash: proposal.content_hash,
            selection: proposal.content.recommendation,
          },
        });
      expect(approval.status()).toBe(200);
      project = await approval.json();
    }
    await page.goto("/?view=meetings");
    await page
      .getByLabel("Tool execution project", { exact: true })
      .selectOption(project!.id);
    const agent = snapshot.agents.find((a) => a.role === "CTO")!;
    await page
      .getByLabel("Tool execution agent", { exact: true })
      .selectOption(agent.id);
    await page
      .getByLabel("Tool model override", { exact: true })
      .selectOption(model.id);
    await page
      .getByLabel("Tool execution objective", { exact: true })
      .fill("Save a scoped architecture decision without any external action");
    await page
      .getByRole("button", { name: "Queue native tool execution", exact: true })
      .click();
    await expect
      .poll(async () => {
        snapshot = await state(page);
        const job = snapshot.agent_work.find(
          (w) => w.kind === "tools" && w.input.model_override === model.id,
        );
        if (job && !queued.includes(job.id)) queued.push(job.id);
        return snapshot.workflows.find((w) => w.id === job?.workflow_id)
          ?.status;
      })
      .toBe("waiting_for_free_provider");
    await page.reload();
    const panel = page.locator("section").filter({
      has: page.getByRole("heading", {
        name: "Native tool execution",
        exact: true,
      }),
    });
    await panel.locator("details").first().locator("summary").click();
    await expect(
      panel.getByText("waiting_for_free_provider", { exact: true }).first(),
    ).toBeVisible();
    await panel
      .getByRole("button", { name: "Cancel execution", exact: true })
      .first()
      .click();
    await expect
      .poll(
        async () =>
          (await state(page)).workflows.find(
            (w) =>
              w.id ===
              snapshot.agent_work.find((j) => j.id === queued[1])?.workflow_id,
          )?.status,
      )
      .toBe("cancelled");
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(async () =>
        page
          .locator(".sidebar")
          .evaluate((e) => e.getBoundingClientRect().right),
      )
      .toBeLessThanOrEqual(1);
    await panel.evaluate((element) =>
      element.scrollIntoView({ block: "start", behavior: "instant" }),
    );
    await page.evaluate(() => window.scrollBy(0, -76));
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(391);
    await page.screenshot({
      path: "../../artifacts/native-tools-mobile.png",
      fullPage: false,
      animations: "disabled",
    });
    const ids = new Set(
      snapshot.agent_work
        .filter((j) => queued.includes(j.id))
        .map((j) => j.workflow_id),
    );
    expect(snapshot.runs.filter((r) => ids.has(r.workflow_id))).toHaveLength(0);
  } finally {
    for (const id of queued)
      await page
        .context()
        .request.post(`/api/agent-work/${id}/cancel`, { headers, data: {} });
    await page.context().request.patch(`/api/providers/${provider.id}`, {
      headers,
      data: { enabled: false },
    });
  }
});
