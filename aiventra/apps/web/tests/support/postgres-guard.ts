import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

export default function guard() {
  if (
    process.env.CI !== "true" ||
    !/^browser_ci_\d+_\d+$/.test(process.env.BROWSER_CI_DATABASE || "")
  )
    throw new Error("Unsafe PostgreSQL browser environment");
  execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "api",
      "python",
      "-c",
      "from company_os.config import settings; from company_os.db import make_application_engine; c=settings(); assert c.isolated_postgres_ci and c.isolated_test_environment; e=make_application_engine(c); assert e.dialect.name=='postgresql'; e.dispose()",
    ],
    { cwd: resolve("../.."), stdio: "pipe" },
  );
}
