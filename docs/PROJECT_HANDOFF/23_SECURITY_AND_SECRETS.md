# Security and Secrets

## Rules

- **NEVER COMMIT API KEYS, tokens, passwords, private SSH keys, cookies, private service-account
  JSON, signed URLs, exchange secrets, or account identifiers not intended for publication.**
- Runtime values belong in environment variables or an approved secret manager, never source,
  config TOML, docs, manifests, shell history, screenshots, or logs.
- `.env.example` documents that public Phase 1/Phase 7 market endpoints need no credential;
  real `.env`/`secrets/` content must stay ignored.
- Binance public acquisition requires no account key. Any future private Binance/account/order
  adapter requires separate authorization, least privilege, key rotation, no withdrawal permission,
  IP restrictions where suitable, and audited secret injection.
- GCE uses the VM service-account identity; never download/commit a service-account private key.
- GitHub access should use an owner-managed SSH/deploy key or credential helper outside the repo;
  never paste a private key into documentation or VM metadata reports.

## Historical incident

The pre-training certification records that a plaintext scratch file containing
`SEEKAI_API_KEY` was remediated and ignored, and that no high-confidence tracked/workspace secret
file remained at that scan. It also says the owner should rotate the credential if it reached chat,
logs, backup, or another shared system. The secret value is intentionally not reproduced here.

Legacy CoinSwitch files can expose credential/account/order concepts and must not be run. They are
excluded from the installable package and retained only for audit/extraction of exchange-independent
ideas.

Before every commit or archive, scan staged/new files for common key/token/private-key patterns and
inspect findings manually. A clean regex scan reduces risk but does not prove that arbitrary
credentials are absent.
