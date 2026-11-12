import { testOrigin } from "./support/environment";
import { loginOwner } from "./support/login";
import { test, expect } from "@playwright/test";
import type { State } from "../src/lib/types";

const headers = { Origin: testOrigin };

test("zero-cost policy shows backend decisions and refuses unsafe resumption on desktop and mobile", async ({
  page,
}) => {
  await loginOwner(page.context().request);
  const initial: State = await (
    await page.context().request.get("/api/state")
  ).json();
  expect(initial.runtime.ai_spending_mode).toBe("ZERO_COST_ONLY");
  const providerResponse = await page.context().request.post("/api/providers", {
    headers,
    data: {
      name: `Policy fixture ${Date.now()}`,
      kind: "openai",
      base_url: "https://api.openai.com/v1",
      credential_env: "ZERO_COST_BROWSER_UNCONFIGURED_API_KEY",
    },
  });
  expect(providerResponse.status()).toBe(201);
  const provider = await providerResponse.json();
  const modelResponse = await page.context().request.post("/api/models", {
    headers,
    data: {
      provider_id: provider.id,
      identifier: `claimed-free-${Date.now()}`,
      capabilities: ["structured"],
      context_tokens: 65536,
      quality: 95,
      reliability: 100,
      input_price_micro_per_million: 0,
      output_price_micro_per_million: 0,
      price_source: "https://example.test/unverified-free-claim",
      sensitivity: "confidential",
    },
  });
  expect(modelResponse.status()).toBe(201);
  const requirement = await page.context().request.post("/api/requirements", {
    headers,
    data: {
      client_id: initial.clients[0].id,
      title: `Zero-cost browser ${Date.now()}`,
      text: "Preserve my requirement while no free model is available",
      mode: "live",
    },
  });
  expect(requirement.status()).toBe(201);
  const record = await requirement.json();
  await expect
    .poll(async () => {
      const state: State = await (
        await page.context().request.get("/api/state")
      ).json();
      return state.workflows.find(
        (workflow) => workflow.id === record.workflow_id,
      )?.status;
    })
    .toBe("waiting_for_free_provider");
  try {
    await page.goto("/?view=models");
    await expect(
      page.getByText("ZERO-COST AI MODE", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "Zero-cost inference policy",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText("UNKNOWN_COST_BLOCKED", { exact: true }).first(),
    ).toBeVisible();
    const saved = page.locator(`[data-workflow-id="${record.workflow_id}"]`);
    await saved.getByRole("button", { name: "Resume saved work" }).click();
    await expect(page.locator(".alert.error")).toContainText(
      "No eligible verified local model; saved workflow remains waiting",
    );
    await page.screenshot({
      path: "../../artifacts/zero-cost-desktop.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("heading", {
        name: "Zero-cost inference policy",
        exact: true,
      }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "../../artifacts/zero-cost-mobile.png",
      fullPage: true,
    });
    const current: State = await (
      await page.context().request.get("/api/state")
    ).json();
    expect(
      current.runs.filter((run) => run.workflow_id === record.workflow_id),
    ).toHaveLength(0);
    expect(
      current.workflows.find((workflow) => workflow.id === record.workflow_id)
        ?.status,
    ).toBe("waiting_for_free_provider");
  } finally {
    // Pause only this test's workflow; retain requirement and append-only audit evidence.
    const paused = await page
      .context()
      .request.post(`/api/workflows/${record.workflow_id}/control`, {
        headers,
        data: { action: "pause" },
      });
    expect(paused.status()).toBe(200);
  }
});
