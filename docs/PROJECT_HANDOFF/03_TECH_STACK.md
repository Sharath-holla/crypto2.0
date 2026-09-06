# Technology Stack

## Verified current stack

| Technology | Why / where used | Removal or replacement consequence |
| --- | --- | --- |
| Python `>=3.11` | Package, CLI, data, research, supervisors | All application and research code depends on it |
| `uv` + `uv.lock` | Reproducible environments and command execution | Unpinned resolution could change numerical/runtime behavior |
| PyArrow / Parquet | Columnar tables, partitioned Bronze/Silver/Gold, batch scans | Replacing requires schema, precision, hash and performance equivalence |
| NumPy | Vectorized features, matrices, metrics, model interfaces | Most feature/model logic would require rewrite |
| LightGBM | Deterministic G0/C0/P0/H0 regression benchmark | Changing model family creates a new experiment |
| scikit-learn | StandardScaler/K-means and supporting research utilities | Cluster identity/preprocessing behavior would change |
| joblib | Serialized `Phase7ModelBundle` artifacts | Existing models/load contract would be incompatible |
| Pydantic | Frozen configuration, registry, universe and contract validation | Fail-closed schema validation would be lost |
| httpx | Official public HTTP clients | Acquisition/context networking needs an equivalent audited client |
| pytest | Unit, integration, adversarial scientific and operational tests | Scientific contracts would lose executable verification |
| Ruff | Lint/import/format checks | Style/static gate would change |
| TOML / JSON | Human configs and machine manifests/checkpoints | Identity and tooling contracts depend on canonical representations |
| Git / GitHub remote | Source history, freezes, annotated tags, collaboration | Reproducibility and audit lineage would be impaired |
| Bash / PowerShell | Linux guest workers and Windows control-plane scripts | Operational launch/watchdog procedures need equivalents |
| tmux / systemd | Historical detached worker/session supervision on Ubuntu VM | Unattended execution model changes; systemd was used cautiously after launch defects |
| Google Compute Engine | Linux environment for heavy multi-symbol work | Laptop execution is explicitly prohibited for this workload |
| GCE persistent disk | Only current location of Phase 7A Gold | Loss/deletion would require recovery/rebuild |
| Google Cloud Storage | Backups, manifests, hold archives, durable evidence | Off-VM archival layer would be lost |
| Binance public archives/REST | Canonical official market-data evidence | A source change requires a new audited source identity |

DuckDB, Polars, Spark, Iceberg, CatBoost, XGBoost, pandas, and neural frameworks are not direct
Phase 7A project dependencies in `pyproject.toml`. Some are discussed as deferred options; do not
describe them as deployed.

## Package management

`pyproject.toml` defines the installable `crypto-trading-ai` package under `src/`, the `crypto-ai`
CLI, Python floor, runtime dependencies, and `dev` extra (`pytest`, `ruff`). `uv.lock` fixes the
resolved graph. Use `uv sync --extra dev` and `uv run ...`; never hand-edit the lock to conceal a
change. Exact direct versions and host distinctions are in [DEPENDENCY_SNAPSHOT.md](DEPENDENCY_SNAPSHOT.md).

The handoff host verified `uv 0.12.3` and Python 3.12.14. Those are local Windows facts, not a claim
about the stopped VM environment. The VM image license identifies Ubuntu Minimal 24.04 LTS; its
current Python/uv binaries are `UNKNOWN / NOT VERIFIED` while stopped.
