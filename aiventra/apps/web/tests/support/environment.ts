// These credentials belong exclusively to scripts/browser_fixture.py.
// Never read the owner's .env or accept a configured live browser endpoint.
export const fixtureSetting = (name: string) => {
  if (name === "OWNER_EMAIL") return "browser-owner@fixture.test";
  if (name === "OWNER_PASSWORD") return "isolated-browser-password";
  throw new Error("Unsupported browser fixture setting");
};
export const testOrigin =
  process.env.BROWSER_TEST_ORIGIN || "http://localhost:3002";
