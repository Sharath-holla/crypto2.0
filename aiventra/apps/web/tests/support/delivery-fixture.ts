import { expect, type APIRequestContext } from "@playwright/test";
import { randomUUID } from "node:crypto";
import type { State } from "../../src/lib/types";
import { testOrigin } from "./environment";

// All writes use the fenced browser server and real approval/workflow APIs.
// This permits the package test to run alone without depending on another test.
export async function prepareDeliveryReview(request: APIRequestContext) {
  const headers = { Origin: testOrigin };
  const state: State = await (await request.get("/api/state")).json();
  const response = await request.post("/api/requirements", {
    headers,
    data: {
      client_id: state.clients[0].id,
      title: `Standalone package fixture ${randomUUID()}`,
      text: "Document a small operations plan with requirements, architecture and security. Explicit deterministic browser fixture.",
      mode: "mock",
      budget_micro: 5000000,
    },
  });
  expect(response.status()).toBe(201);
  const requirement = await response.json();
  let proposal: State["proposals"][number] | undefined;
  await expect
    .poll(
      async () => {
        const current: State = await (await request.get("/api/state")).json();
        proposal = current.proposals.find(
          (row) => row.requirement_id === requirement.id,
        );
        return !!proposal;
      },
      { timeout: 60000 },
    )
    .toBe(true);
  const accepted = await request.post(
    `/api/proposals/${proposal!.id}/approve`,
    {
      headers,
      data: {
        version: proposal!.version,
        content_hash: proposal!.content_hash,
        selection: proposal!.content.recommendation,
      },
    },
  );
  expect(accepted.status()).toBe(200);
  const project = await accepted.json();
  const plan = await (
    await request.get(`/api/projects/${project.id}/staffing`)
  ).json();
  const changed = await request.patch(`/api/staffing/${plan.id}`, {
    headers,
    data: {
      version: plan.version,
      content: { ...plan.content, mode: "mock" },
    },
  });
  expect(changed.status()).toBe(200);
  const revision = await changed.json();
  expect(
    (
      await request.post(`/api/staffing/${plan.id}/approve`, {
        headers,
        data: {
          version: revision.version,
          content_hash: revision.content_hash,
        },
      })
    ).status(),
  ).toBe(200);
  let sourceHash = "";
  await expect
    .poll(
      async () => {
        const ready = await (
          await request.get(
            `/api/projects/${project.id}/delivery-readiness?mode=mock`,
          )
        ).json();
        sourceHash = ready.source_hash;
        return ready.ready;
      },
      { timeout: 90000 },
    )
    .toBe(true);
  const review = await request.post(
    `/api/projects/${project.id}/final-review`,
    {
      headers,
      data: {
        request_id: randomUUID(),
        source_hash: sourceHash,
        mode: "mock",
      },
    },
  );
  expect(review.status()).toBe(201);
  const reviewId = (await review.json()).review.id;
  let record: State["records"][number] | undefined;
  await expect
    .poll(
      async () => {
        const current: State = await (await request.get("/api/state")).json();
        record = current.records.find((row) => row.id === reviewId);
        return record?.status;
      },
      { timeout: 90000 },
    )
    .toBe("fixture_reviewed");
  return record!;
}
