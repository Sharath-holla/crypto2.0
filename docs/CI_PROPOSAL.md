# CI Proposal (optional — owner decision)

The repository has no CI today. Nothing here is a blocker for Phase 7 training;
the official suite runs in the repository's own `uv` environment on the
training VM. This is a minimal proposal the owner can activate by moving the
workflow below into `.github/workflows/ci.yml` and pushing.

## Why it would help

- The full suite (currently 562 tests incl. the new regression suites) runs in
  ~70 s on a single runner.
- The scientific baseline freeze tests, config-identity gates, holdout guards,
  timing/leakage tests, checkpoint tests and `_pair_stats` equivalence tests
  are byte- and hash-sensitive: a CI failure would catch accidental
  methodology or data-contract drift before it reaches the VM.
- Ruff (E, F, I, UP, B, SIM) is already clean and enforced by the gates.

## Proposed workflow

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv sync --frozen --extra dev
      - run: uv run ruff check src tests scripts
      - run: uv run pytest -q
```

## Notes / risks

- The suite is Linux-oriented (`longdouble` precision in `_pair_stats`, GNU
  `stat` in the log-rotation tests); `ubuntu-latest` matches the VM
  environment.
- No GCS/Binance access is required: cloud-guard tests verify the guards, not
  live services. `PHASE7_ALLOW_CLOUD_RESEARCH` must NOT be set on CI.
- If activated later, a nightly scheduled run would additionally guard
  dependency drift.