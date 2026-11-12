import { testOrigin } from "./environment";
import { fixtureSetting as setting } from "./environment";
import { expect, test, type APIRequestContext } from "@playwright/test";

export async function loginOwner(request: APIRequestContext) {
  return loginAccount(
    request,
    { email: setting("OWNER_EMAIL"), password: setting("OWNER_PASSWORD") },
    testOrigin,
  );
}

export async function loginAccount(
  request: APIRequestContext,
  credentials: { email: string; password: string },
  origin: string,
) {
  // Exercise the real persistent account throttle. Never raise production
  // limits or accept an authentication failure as a successful login.
  const deadline = Date.now() + 65000;
  let waiting = false;
  while (true) {
    const response = await request.post("/api/auth/login", {
      headers: { Origin: origin },
      data: credentials,
    });
    expect([200, 429]).toContain(response.status());
    if (response.status() === 200) return;
    if (!waiting) {
      // Budget only actual rate-limit waiting; preserve every application assertion deadline.
      test.info().setTimeout(test.info().timeout + 65000);
      waiting = true;
    }
    if (Date.now() >= deadline)
      throw new Error("Account login throttle did not clear within 65 seconds");
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
}
