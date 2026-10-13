# Local setup

Run from the Crypto repository on `integration/aiventra-crypto-os`. Do not reset the
scientific branch or copy a historical Lightning checkout over this repository.
Python 3.12, uv, Node.js and npm are required; keep environments separate.

```powershell
uv sync --locked --extra dev
cd aiventra
uv sync --locked --extra dev --python 3.12
cd apps/web
npm ci --ignore-scripts
cd ../../..
.venv/Scripts/python.exe -m integration.crypto_aiventra.dev start
```

On Linux use `.venv/bin/python` for the final command. This does not authorize training
or provision a host. The launcher uses the existing Aiventra bootstrap script to create
private ignored `aiventra/.env` if absent and a separate ignored adapter key profile.
It never prints their values. Owner login credentials are local in `aiventra/.env`;
read them privately, never paste them into chat, logs or source. Existing configuration
is preserved. SQLite is migrated only for the new local application database, then
seeded with the existing workforce. No provider/model key is required for this UI.

Default loopback services:

| Service | Address |
| --- | --- |
| Frontend | http://127.0.0.1:3010 |
| Aiventra API | http://127.0.0.1:8010 |
| Private Crypto adapter | http://127.0.0.1:8011 |

The launcher refuses occupied ports rather than stopping another application. Override
with `--web-port`, `--api-port`, `--adapter-port` if necessary; do not expose these
development servers publicly. Startup launches the workflow heartbeat but no science,
inference, cloud service, model download, provider connection or live trading.

## Paths

`CryptoPaths.from_environment()` is the authoritative explicit mapping. Defaults:

| Variable | Default relative to Crypto root |
| --- | --- |
| `CRYPTO_REPO_ROOT` | repository containing the adapter |
| `CRYPTO_PERSISTENT_ROOT` | `local_artifacts` |
| `CRYPTO_GOLD_ROOT` | `data/gold/phase7a_core20_primary_v1` |
| `CRYPTO_PHASE7_DATA_ROOT` | `data/phase7` |
| `CRYPTO_HISTORICAL_ROOT` | persistent root + `phase7` |
| `CRYPTO_CHECKPOINT_ROOT` | historical root + `checkpoints` |
| `CRYPTO_CACHE_ROOT` | historical root + `prepared_cache` |
| `CRYPTO_MODEL_ROOT` | historical root + `models` |
| `CRYPTO_REPORT_ROOT` | historical root + `reports` |
| `CRYPTO_LOG_ROOT` | historical root + `logs` |
| `CRYPTO_VERIFICATION_ROOT` | historical root + `verification` |
| `CRYPTO_CONTROL_ROOT` | persistent root + `aiventra-control` |

Set actual restored roots explicitly on a future approved host. Path configuration is
server-only, never accepted from browser commands. Control state must not overlap
scientific roots. The adapter translates approved execution roots to the canonical
`PHASE7_*` environment only inside trusted workers. It does not rewrite manifests.
Do not point artifact-browser roots at Gold or Silver or private configuration.

Missing local data remains `AWAITING_EVIDENCE`; the historical quoted 138 Gold partitions,
50,352,548 rows and Silver closure counts are not a live validation result.
No data acquisition is part of local startup. Demo mode is opt-in and restricted to
disposable browser-fixture directories; the normal launcher explicitly removes it.
