# Test strategy

Run the README verification commands after modifying the implementation. Backend tests isolate databases and artifacts under a dedicated workspace test directory. They cover consulting state, exact approval and project creation, dependency dispatch, artifact integrity, recovery across real worker process restarts, concurrent claims and budget reservations, stale approvals, tenant/client isolation, role and tool denials, secret/path controls and official provider HTTP contracts.

Provider tests use clearly identified HTTP fixtures. They exercise fallback, usage accounting, schema-quality escalation and unknown-outcome blocking. They do not prove live credentials, account model availability or actual invoice costs.

Browser tests run against the real local API and worker, sign in through the HttpOnly proxy, submit fixture requirements, review proposals, approve projects, inspect artifacts, verify audit history and inspect an employee. They also check unauthenticated access and write-origin rejection. Browser screenshots/traces remain local and may contain private business records; do not publish them automatically.

Container QA implementation is separate from the test runner and remains unverified without Docker. Test discovery must find at least one test; a zero exit with no tests cannot complete a coding task. Production load, Postgres concurrency, live cloud staging/rollback, adversarial sandbox escape, OAuth connectors and crypto regression tests remain outstanding. See TEST_REPORT.md for the actual latest evidence and limitations.
