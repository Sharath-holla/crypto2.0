# Direct Mac → Claude Code VM transfer (Cloudflare Quick Tunnel)

Owner decision 2026-11-14: no Google Cloud Storage, AWS, Lightning, paid buckets or GitHub for the
dataset. The Mac is the data SOURCE only; all preparation/training runs on the Claude Code VM.

```
Mac: mac_transfer_server.py (127.0.0.1 only, read-only, manifest-only, bearer token, TTL)
  └─ cloudflared quick tunnel (outbound from the Mac) → https://<random>.trycloudflare.com
        └─ Claude Code VM proxy (adds the token from the secure credential card)
              └─ transfer_set.py fetch --base-url … (Range resume, SHA-256 verify, atomic rename)
```

## Security model

| Property | How |
|---|---|
| Only manifest files | Server looks up the exact path in the committed 2,777-file manifest (optionally narrowed by `--batch-file`); everything else → 404; no listing |
| Authentication | 256-bit random bearer token per server start, constant-time compare, file `~/.crypto2-transfer/token` mode 0600, never printed or logged; removed when the server stops |
| Token delivery to the VM | Pasted ONLY into Claude's secure credential card for the exact tunnel hostname; the session proxy injects it. Never in chat, Git, logs or files on the VM |
| Short-lived | `--ttl-minutes` (default 240) → server exits; new start = new token and new hostname |
| Brute force | Server exits after `--max-auth-failures` (default 30) |
| Read-only, originals preserved | Files opened read-only; nothing written on the Mac except the token and access log under `~/.crypto2-transfer/` |
| Exposure | Server binds 127.0.0.1; only the tunnel reaches it; stop either process (Ctrl-C) to close access immediately |
| Integrity | Server sends the manifest SHA-256; the VM rejects a mismatch, verifies SHA-256 of every downloaded file, renames atomically |
| Caveat | Cloudflare terminates TLS at its edge, so Cloudflare can technically see the bytes and the token in transit. The data is Binance-derived market data; if that is unacceptable, do not use this method |
| Repository | Public: no token, hostname, log or data file is committed (`.gitignore` covers run outputs) |

Quick Tunnels are a free Cloudflare service intended for testing: no account, no uptime
guarantee, a new random hostname on every start (which needs a new credential card).

## Mac commands

```bash
git -C /Users/cortex/Projects/crypto2.0 fetch origin experiment/phase7-cloud-training-prep
```

```bash
git -C /Users/cortex/Projects/crypto2.0 worktree add /Users/cortex/Projects/crypto2.0-cloudprep origin/experiment/phase7-cloud-training-prep
```

```bash
brew install cloudflared
```

Terminal 1 — server (first test: one file only, 60 minutes):

```bash
cd /Users/cortex/Projects/crypto2.0-cloudprep && mkdir -p ~/.crypto2-transfer && echo "crypto2-persistent/data/phase7/bronze/binance/manifests/reconciled-gap-usdm-filusdt-1d-de35246d2b3d2102f8332e61.json" > ~/.crypto2-transfer/batch-test.txt
```

```bash
python3 scripts/cloud/mac_transfer_server.py --root /Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107 --batch-file ~/.crypto2-transfer/batch-test.txt --ttl-minutes 60 --verify-sha256
```

Full transfer later (all 2,777 files): the same command without `--batch-file`, with
`--ttl-minutes 240`.

Terminal 2 — tunnel (prints `https://<random>.trycloudflare.com`):

```bash
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8765
```

Terminal 3 — prove that unauthenticated access is refused (expect `401` twice):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<random>.trycloudflare.com/healthz
```

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<random>.trycloudflare.com/files/crypto2-persistent/data/phase7/bronze/binance/manifests/reconciled-gap-usdm-filusdt-1d-de35246d2b3d2102f8332e61.json
```

Copy the token to the clipboard for the credential card (never paste it into chat):

```bash
pbcopy < ~/.crypto2-transfer/token
```

Stop everything immediately: Ctrl-C in Terminal 2 (tunnel) and Terminal 1 (server). Cleanup:

```bash
rm -f ~/.crypto2-transfer/token ~/.crypto2-transfer/batch-test.txt
```

## VM commands (Claude)

```bash
uv run python scripts/cloud/transfer_set.py fetch --root /home/user/crypto2data/staging --base-url https://<random>.trycloudflare.com --path crypto2-persistent/data/phase7/bronze/binance/manifests/reconciled-gap-usdm-filusdt-1d-de35246d2b3d2102f8332e61.json --execute
```

Full set (resumable; re-run to continue; verified files are skipped):

```bash
uv run python scripts/cloud/transfer_set.py fetch --root /home/user/crypto2data/staging --base-url https://<random>.trycloudflare.com --execute
```

```bash
uv run python scripts/cloud/transfer_set.py verify --root /home/user/crypto2data/staging --record /home/user/crypto2run/evidence/transfer_verification.json
```

Batches: `--batch-file FILE` on BOTH sides (server serves only that batch; VM fetches only it).

## Batching and deletion rules

* Every Gold partition must be present and checksum-verified for any preparation or training
  run (the loader verifies the whole Gold manifest), so source data is transferred in batches
  but is NOT deleted batch-by-batch while any fold still needs it.
* Disposable VM-side files: `.part` files, spill directories (deleted automatically when a run
  ends) and prepared caches (released with `low_memory_disk release` only after all of their
  specifications are terminal and results are persisted).
* The Mac originals are never modified or deleted.
