# Dependency Snapshot

## Locked direct dependencies

Extracted from `uv.lock` on 2026-09-06:

| Package | Locked version |
| --- | ---: |
| httpx | 0.28.1 |
| joblib | 1.5.3 |
| LightGBM | 4.7.0 |
| NumPy | 2.4.6 |
| PyArrow | 24.0.0 |
| Pydantic | 2.13.4 |
| scikit-learn | 1.9.0 |
| pytest (`dev`) | 9.1.1 |
| Ruff (`dev`) | 0.16.3 |
| msvc-runtime (Windows) | 14.44.35112 |
| tzdata (Windows) | 2026.3 |

Project metadata requires Python `>=3.11`. The handoff workstation verified Python **3.12.14** and
`uv 0.12.3`; these are Windows-host values, not frozen VM binary versions. The VM image is verified
as Ubuntu Minimal **24.04 LTS**, machine `e2-standard-16` (16 vCPU), with prior approximately
62–64 GiB guest RAM observations. Exact stopped-VM Python/uv versions are **UNKNOWN / NOT VERIFIED**.

Use `uv sync --extra dev` from the lock. Any dependency upgrade is a controlled change: rerun full
Linux scientific/serialization/checkpoint tests and create new cache identities where numerical,
ABI, schema, or artifact compatibility can change.
