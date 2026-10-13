# Existing repository and crypto integration

No crypto repository was supplied during the initial build. No exchange, network, strategy or deployment stack is assumed.

1. Back up your actual repository and keep your existing changes. Place a copy inside `REPOSITORY_ROOT` (default `data/repositories`). Do not copy wallet secrets or live exchange credentials.
2. Create/approve the consulting plan for this project. In Engineering, register the repository using its relative path.
3. Discovery reads directory/language counts, manifests, test file locations and Git HEAD. It excludes secret files and does not execute the repository. Baseline tests are explicitly **not run** during discovery.
4. Inspect the discovery report. Activate optional crypto specialists if relevant.
5. Create a coding task with concrete acceptance criteria, approved test suite, mode and cost cap. The owner separately approves its exact payload hash.
6. The worker requires a clean baseline commit, creates a detached isolated Git worktree, and attempts baseline tests only through the restricted runner. Original files remain unchanged.
7. A configured coding model produces validated files. A separate code reviewer sees the actual tracked diff and proposed file content. A separate QA agent runs approved regression tests and stores exit code, environment, timestamps, commit and logs.
8. A task cannot be completed by its author. Fixture reviewers never certify a real change. Missing Docker, failed tests or rejected review create blocked/failed work and owner attention.

Built-in commands currently support Python's standard-library unittest and Node's built-in test runner. Allowlisted package installation, framework-specific commands, coverage, repair loops, commits, merge queues, GitHub import/PR creation and ZIP import remain pending. Existing repository metadata must be reviewed before enabling execution.

Testnet/sandbox use is the default crypto policy. Live trading, transfers and wallets are not connected. Never place private keys or seed phrases into LLM context. Financial projections must be estimates and trading approval controls need a separately verified connector before any real financial effect is possible.

Worktree cleanup is deliberately manual so unmerged artifacts are preserved. Review worktree diffs and copy/merge approved changes through your normal Git workflow. Do not delete source repositories or run `git reset --hard` to prepare them.
