import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

function snapshot() {
  return execFileSync(
    resolve(
      process.env.BROWSER_FIXTURE_PYTHON || "../../.venv/Scripts/python.exe",
    ),
    ["scripts/browser_registry_snapshot.py"],
    { cwd: resolve("../.."), encoding: "utf8" },
  ).trim();
}
export default function setup() {
  const file = resolve(
    "../../data/pytest-temp/browser-registry-" + crypto.randomUUID() + ".json",
  );
  process.env.BROWSER_REGISTRY_SNAPSHOT = file;
  writeFileSync(file, snapshot());
}
export function verifyRegistryUnchanged() {
  const file = process.env.BROWSER_REGISTRY_SNAPSHOT;
  if (!file || readFileSync(file, "utf8") !== snapshot())
    throw new Error("Developer registry changed during isolated browser tests");
}
