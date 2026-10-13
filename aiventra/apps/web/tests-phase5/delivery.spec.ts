import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { loginAccount } from "../tests/support/login";

type Fixture = {
  packages: Record<
    string,
    {
      project_id: string;
      id: string;
      version: number;
      manifest_hash: string;
      client_email: string;
    }
  >;
  unredeemed_invitation: string;
};
const fixture = () =>
  JSON.parse(
    readFileSync("../../data/phase5-browser-state.json", "utf8"),
  ) as Fixture;
const origin = { Origin: "http://localhost:3001" };
async function login(request: APIRequestContext, role: "owner" | "client") {
  await loginAccount(
    request,
    {
      email:
        role === "owner"
          ? "phase5-owner@fixture.test"
          : fixture().packages.acceptance.client_email,
      password:
        role === "owner"
          ? "phase5-fixture-owner-password"
          : "private-fixture-client-password",
    },
    origin.Origin,
  );
}
async function ownerProject(page: Page, name: string) {
  await login(page.request, "owner");
  await page.goto(
    `/?view=projects&project=${fixture().packages[name].project_id}`,
  );
  await page.getByRole("button", { name: "Delivery", exact: true }).click();
}
async function releaseThroughUI(page: Page, name: string) {
  await ownerProject(page, name);
  const item = page.getByRole("region", {
    name: "Delivery package version 1",
    exact: true,
  });
  await item
    .getByText("Owner release authority · separate from final review", {
      exact: true,
    })
    .click();
  await item
    .getByLabel("Owner decision reason")
    .fill(
      "Owner reviewed the exact isolated fixture package and intended recipients.",
    );
  await expect(
    item.getByRole("button", { name: "Approve exact release", exact: true }),
  ).toBeEnabled();
  await item
    .getByRole("button", { name: "Approve exact release", exact: true })
    .click();
  await expect(
    item.getByRole("button", { name: "Release approved package", exact: true }),
  ).toBeEnabled();
  await item
    .getByRole("button", { name: "Release approved package", exact: true })
    .click();
  await expect(
    item.locator(".badge").filter({ hasText: /^released$/ }),
  ).toBeVisible();
}

test.describe.configure({ mode: "serial" });
test.beforeEach(async ({ page }) => {
  page.on("dialog", (dialog) => dialog.accept());
});

test("exact owner release, filtered client download, formal acceptance and approved closure", async ({
  page,
}) => {
  await releaseThroughUI(page, "acceptance");
  await login(page.request, "client");
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Client workspace", exact: true }),
  ).toBeVisible();
  const item = page.getByRole("region", {
    name: "Released delivery version 1",
    exact: true,
  });
  await expect(
    item.getByText(
      `Manifest SHA-256: ${fixture().packages.acceptance.manifest_hash}`,
      { exact: true },
    ),
  ).toBeVisible();
  const link = item.getByRole("link").first();
  const href = await link.getAttribute("href");
  const download = await page.request.get(href!);
  expect(download.ok()).toBeTruthy();
  expect(download.headers()["cache-control"]).toContain("no-store");
  const digest = createHash("sha256")
    .update(await download.body())
    .digest("hex");
  await expect(item.getByText(digest, { exact: true })).toBeVisible();
  expect(
    (
      await page.request.get(
        `/api/delivery-packages/${fixture().packages.acceptance.id}`,
      )
    ).status(),
  ).toBe(403);
  await item.getByText("Respond to version 1", { exact: true }).click();
  await item
    .getByLabel("Reason or feedback")
    .fill(
      "I accept this exact controlled fixture version and its stated limitations.",
    );
  await item
    .getByLabel("I confirm this response applies", { exact: false })
    .check();
  await item
    .getByRole("button", { name: "Submit client response", exact: true })
    .click();
  await expect(
    item.getByText("A formal decision is already saved.", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByText("Client decisions and acceptance history", { exact: true })
    .click();
  await expect(
    page.getByText(
      "I accept this exact controlled fixture version and its stated limitations.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../../artifacts/client-delivery-portal.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await ownerProject(page, "acceptance");
  const followups = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "Client follow-ups and project closure",
      exact: true,
    }),
  });
  await followups
    .getByText("Owner project closure gate", { exact: true })
    .click();
  await expect(
    followups.getByRole("button", { name: "Approve exact project closure" }),
  ).toBeEnabled();
  await followups
    .getByRole("button", { name: "Approve exact project closure" })
    .click();
  await expect(
    followups.getByRole("button", { name: "Close accepted project" }),
  ).toBeEnabled();
  await followups
    .getByRole("button", { name: "Close accepted project" })
    .click();
  await expect(
    followups.locator(".badge").filter({ hasText: /^closed$/ }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("client change request persists and owner schedules bounded impact analysis and follow-up", async ({
  page,
}) => {
  await releaseThroughUI(page, "changes");
  await login(page.request, "client");
  await page.goto("/");
  const item = page
    .getByRole("region", { name: "Released delivery version 1" })
    .filter({ hasText: fixture().packages.changes.manifest_hash });
  await item.getByText("Respond to version 1", { exact: true }).click();
  await item
    .getByRole("combobox", { name: /^Response/ })
    .selectOption("request_changes");
  await item
    .getByLabel("Reason or feedback")
    .fill(
      "Please revise the controlled documentation fixture to explain the acceptance criteria.",
    );
  await item
    .getByLabel("I confirm this response applies", { exact: false })
    .check();
  await item
    .getByRole("button", { name: "Submit client response", exact: true })
    .click();
  await expect(
    item.getByText("A formal decision is already saved.", { exact: false }),
  ).toBeVisible();
  await ownerProject(page, "changes");
  const card = page.getByRole("region", {
    name: "Client request changes · v1",
    exact: true,
  });
  await card.getByLabel("Analysis execution").selectOption("mock");
  await card
    .getByRole("button", { name: "Assign saved impact analysis" })
    .click();
  await expect(
    card.getByRole("button", { name: "Approve exact analyzed scope" }),
  ).toBeEnabled({ timeout: 45000 });
  await card
    .getByLabel("Reviewed impact summary")
    .fill(
      "Controlled documentation follow-up with no live AI or real completion claim.",
    );
  await card
    .getByLabel("Affected components", { exact: false })
    .fill("documentation");
  await card
    .getByLabel("Follow-up acceptance criteria", { exact: false })
    .fill("Provide verifiable documentation evidence");
  await card
    .getByRole("button", { name: "Approve exact analyzed scope" })
    .click();
  await card.getByLabel("Follow-up component").selectOption("documentation");
  await card
    .getByRole("button", { name: "Create approved follow-up tasks" })
    .click();
  await expect(
    card.getByText("engineering_pending", { exact: true }),
  ).toBeVisible();
  await expect(card.getByText("completed", { exact: true })).toBeVisible({
    timeout: 45000,
  });
  await card
    .getByLabel("Client-facing resolution summary")
    .fill(
      "Deterministic fixture work is saved and checked; live delivery remains blocked.",
    );
  await card
    .getByRole("button", { name: "Verify completed work and resolve case" })
    .click();
  await expect(
    card.getByText("fixture_verified", { exact: true }),
  ).toBeVisible();
});

test("defect reporting retains severity and reproduction; deterministic package cannot release", async ({
  page,
}) => {
  await releaseThroughUI(page, "defect");
  await login(page.request, "client");
  await page.goto("/");
  const item = page
    .getByRole("region", { name: "Released delivery version 1" })
    .filter({ hasText: fixture().packages.defect.manifest_hash });
  await item.getByText("Respond to version 1", { exact: true }).click();
  await item
    .getByRole("combobox", { name: /^Response/ })
    .selectOption("report_defect");
  await item
    .getByLabel("Reason or feedback")
    .fill(
      "Controlled fixture defect: the documentation needs an independently verified correction.",
    );
  await item
    .getByLabel("Reproduction steps", { exact: false })
    .fill("Open the fixture document and compare the acceptance criteria.");
  await item.getByLabel("Severity").selectOption("high");
  await item
    .getByLabel("Supporting text files", { exact: false })
    .setInputFiles({
      name: "defect-fixture.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Controlled defect log fixture"),
    });
  await item
    .getByLabel("I confirm this response applies", { exact: false })
    .check();
  await item
    .getByRole("button", { name: "Submit client response", exact: true })
    .click();
  await expect(
    item.getByText("Statement saved", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await page.getByText("Changes, defects and support", { exact: true }).click();
  await expect(
    page
      .getByText("Changes, defects and support", { exact: true })
      .locator("..")
      .getByText(
        "Controlled fixture defect: the documentation needs an independently verified correction.",
        { exact: true },
      ),
  ).toBeVisible();
  const evidence = await page.request.get(
    (await page
      .getByRole("link", { name: "defect-fixture.txt", exact: true })
      .getAttribute("href"))!,
  );
  expect(evidence.ok()).toBeTruthy();
  expect(await evidence.text()).toBe("Controlled defect log fixture");
  await ownerProject(page, "fixture");
  const blocked = page.getByRole("region", {
    name: "Delivery package version 1",
    exact: true,
  });
  await blocked
    .getByText("Owner release authority · separate from final review", {
      exact: true,
    })
    .click();
  await expect(
    blocked.getByText("Deterministic fixture packages can never be released", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    blocked.getByRole("button", { name: "Approve exact release", exact: true }),
  ).toBeDisabled();
});

test("single-use invitation redemption creates only its scoped client workspace", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByText("Redeem an owner invitation", { exact: true }).click();
  await page
    .getByLabel("Invited email", { exact: true })
    .fill("new-browser-client@fixture.test");
  await page
    .getByLabel("Private invitation token", { exact: true })
    .fill(fixture().unredeemed_invitation);
  await page
    .getByLabel("Client password", { exact: true })
    .fill("new-client-fixture-private-password");
  await page
    .getByRole("button", { name: "Redeem invitation and sign in" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Client workspace", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "No released packages", exact: true }),
  ).toBeVisible();
  expect((await page.request.get("/api/client/projects")).ok()).toBeTruthy();
  expect((await page.request.get("/api/state")).status()).toBe(403);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
