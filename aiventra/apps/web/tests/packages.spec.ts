import { test, expect } from "@playwright/test";
import { loginOwner } from "./support/login";
import { prepareDeliveryReview } from "./support/delivery-fixture";
import type { State } from "../src/lib/types";

test("owner prepares a real frozen fixture package with verified downloads and reload", async ({
  page,
}) => {
  test.setTimeout(240000);
  const request = page.context().request;
  await loginOwner(request);
  const state: State = await (await request.get("/api/state")).json();
  const reviews = state.records.filter(
    (row) =>
      row.kind === "delivery_review" && row.status === "fixture_reviewed",
  );
  let selected: (typeof reviews)[number] | undefined;
  for (const review of reviews) {
    const evidence = await (
      await request.get(
        `/api/projects/${review.project_id}/delivery-readiness?mode=mock`,
      )
    ).json();
    if (evidence.ready && evidence.source_hash === review.data.source_hash) {
      selected = review;
      break;
    }
  }
  if (!selected) selected = await prepareDeliveryReview(request);
  expect(
    selected,
    "Existing final-review browser fixture must remain available",
  ).toBeTruthy();
  const review = selected!;
  await page.goto(`/?view=projects&project=${review.project_id}`);
  await page.getByRole("button", { name: "Delivery", exact: true }).click();
  const panel = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "Immutable delivery packages",
      exact: true,
    }),
  });
  await panel.getByLabel("Completed final review").selectOption(review.id);
  await panel
    .getByLabel("Client delivery summary")
    .fill(
      "Explicit deterministic browser package fixture; never a live client release.",
    );
  await panel
    .getByLabel("Release notes", { exact: true })
    .fill(
      "Real saved fixture documents, frozen hashes and worker preparation checkpoints.",
    );
  await panel
    .getByLabel("Owner-provided test summary")
    .fill(
      "Five deterministic reviews saved; live AI and deployment remain unverified.",
    );
  await panel
    .getByLabel("Known limitations", { exact: false })
    .fill("Deterministic fixture only. No client release authorized.");
  await panel
    .getByText("Map reviewed documents and client visibility", { exact: true })
    .click();
  const source = review.data.manifest as { sources: { artifact_id: string }[] };
  for (const purpose of [
    "architecture_decisions",
    "high_level_design",
    "low_level_design",
    "database",
    "api",
    "deployment_instructions",
  ]) {
    await panel
      .getByLabel(`Document for ${purpose}`, { exact: true })
      .selectOption(source.sources[0].artifact_id);
  }
  const createdResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response
        .url()
        .endsWith(`/api/projects/${review.project_id}/delivery-packages`),
  );
  await panel
    .getByRole("button", { name: "Prepare immutable package", exact: true })
    .click();
  const response = await createdResponse;
  expect(response.status()).toBe(201);
  const created = await response.json();
  await expect
    .poll(
      async () => {
        const item = await (
          await request.get(`/api/delivery-packages/${created.id}`)
        ).json();
        return item.status;
      },
      { timeout: 30000 },
    )
    .toBe("package_ready");
  const saved = await (
    await request.get(`/api/delivery-packages/${created.id}`)
  ).json();
  expect(saved.classification).toBe("fixture_nonproduction");
  expect(saved.integrity_valid).toBe(true);
  expect(saved.workflow.step).toBe(2);
  expect(saved.manifest.files).toHaveLength(10);
  const file = saved.manifest.files[0];
  const download = await request.get(
    `/api/delivery-packages/${saved.id}/files/${file.id}`,
  );
  expect(download.status()).toBe(200);
  expect(download.headers()["content-disposition"]).toContain("attachment");
  expect(await download.text()).toContain("acceptance");
  await page.reload();
  await page.getByRole("button", { name: "Delivery", exact: true }).click();
  const version = page.getByRole("region", {
    name: `Delivery package version ${saved.version}`,
    exact: true,
  });
  await expect(
    version.getByText("All frozen files verified", { exact: true }),
  ).toBeVisible();
  await expect(
    version.getByText(`Manifest SHA-256: ${saved.manifest_hash}`, {
      exact: true,
    }),
  ).toBeVisible();
  await version
    .getByText("Inspect frozen manifest and files", { exact: true })
    .click();
  await expect(
    version.getByRole("link", {
      name: "Approved requirements.json",
      exact: true,
    }),
  ).toBeVisible();
  const deployment = page.getByRole("region", {
    name: "Deployment orchestration",
    exact: true,
  });
  await expect(deployment).toContainText("SIMULATED_NONPRODUCTION");
  await deployment
    .getByRole("button", { name: "Refresh deployment evidence", exact: true })
    .click();
  const resume = deployment.getByRole("button", {
    name: "Resume company deployments",
    exact: true,
  });
  if (await resume.isVisible()) await resume.click();
  await deployment
    .getByText("Create a simulation target", { exact: true })
    .click();
  await deployment
    .getByLabel("Target name", { exact: true })
    .fill("Browser staging simulation");
  const targetResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/projects/${review.project_id}/deployment-targets`) &&
      r.request().method() === "POST",
  );
  await deployment
    .getByRole("button", { name: "Save simulation target", exact: true })
    .click();
  const targetResult = await targetResponse;
  expect(targetResult.status()).toBe(201);
  const target = await targetResult.json();
  await deployment
    .getByLabel("Frozen release package", { exact: true })
    .selectOption(saved.id);
  await deployment
    .getByLabel("Deployment target", { exact: true })
    .selectOption(target.id);
  const planResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/projects/${review.project_id}/deployment-plans`) &&
      r.request().method() === "POST",
  );
  await deployment
    .getByRole("button", { name: "Prepare deployment plan", exact: true })
    .click();
  const planResult = await planResponse;
  expect(planResult.status()).toBe(201);
  const plan = await planResult.json();
  await deployment
    .getByRole("button", {
      name: "Approve exact staging deploy simulation",
      exact: true,
    })
    .click();
  await deployment
    .getByRole("button", { name: "Run approved simulation", exact: true })
    .click();
  await expect
    .poll(
      async () => {
        const data = await (
          await request.get(`/api/projects/${review.project_id}/deployments`)
        ).json();
        return data.receipts.find(
          (r: { data: { body: { plan_id: string } } }) =>
            r.data.body.plan_id === plan.id,
        )?.integrity_valid;
      },
      { timeout: 30000 },
    )
    .toBe(true);
  await deployment
    .getByRole("button", { name: "Refresh deployment evidence", exact: true })
    .click();
  await expect(deployment).toContainText("deployment_completed");
  await expect(deployment).toContainText(
    "Simulation cannot release a client package",
  );
  await page.reload();
  await page.getByRole("button", { name: "Delivery", exact: true }).click();
  await expect(deployment).toContainText("deployment_completed");
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("heading", { name: "Immutable delivery packages", exact: true })
    .click();
  await page.keyboard.press("Escape");
  await page.screenshot({
    path: "../../artifacts/deployment-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../artifacts/delivery-packages.png",
    fullPage: true,
  });
});
