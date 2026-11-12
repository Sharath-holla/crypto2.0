# Backup and recovery status

## Milestone 2 transfer/recovery increment

Actual published source **af5b85c** passed the [CI restore drill](https://github.com/Sharath-holla/Aiventra/actions/runs/38018391046): all 52 table digests matched after a real PostgreSQL-container restart and restoration into a separate database; service readiness passed afterward. This does not migrate the workstation or certify offsite/PITR/crash recovery.

The new transfer tool retains private, consistent SQLite snapshots and validates integrity/FK/audit/schema plus encrypted vault decryptability when credentials exist. The current workstation snapshot preserved 52 tables and 14,257 rows at capture. Apply holds a source write lock and rolls back destination schema/data on failure. DATABASE_MIGRATION.md describes explicit cutover and why switching to stale SQLite after PostgreSQL writes is unsafe. File artifacts/repositories and the vault key require separate private preservation; the tool does not copy them.

CI now includes an actual PostgreSQL-container restart with writers stopped, then a custom pg_dump restored into a **separate database** and all-table digest comparison before restarting services. See TEST_REPORT.md for the source/run result. Backups remain unencrypted/private and no offsite/PITR/crash-kill recovery is certified. Older sections below describe earlier evidence; their missing database-restart/restore drill has been addressed in CI only when the new source run passes.

Before the local zero-cost migration, the managed services were stopped and Python sqlite3 online backup created a private snapshot under `data/backups/`. SQLite `quick_check` passed. All row counts across 51 preexisting tables matched after additive migration to `a31d07edc482`; no records were reset. Keep backups outside Git with restricted access. This snapshot is not encrypted and is not an offsite backup service.

For restore, stop managed services, back up the current database first, restore to a separate candidate file, run integrity/migration checks and verify scoped business records before explicitly changing the configured path. Do not overwrite the active database during an unverified restore. Preserve the private vault key, artifacts and repository data in encrypted backups; never publish them.

Actual service restart comparisons exist for PostgreSQL/pgvector memory, conversations, staffing and runner results in GitHub Actions. `scripts/verify_zero_cost_recovery.py` adds digest comparison of saved zero-cost waits and verification records. These restart checks are not disaster-recovery restoration drills. Automated encrypted PostgreSQL backups, PITR, retention and offsite restore drills remain incomplete.

The current Compose comparison restarts API/worker/web while PostgreSQL retains its named volume; the database container itself is not restarted by that check. A database crash/restart and backup restoration drill remains a separate next-step requirement.
