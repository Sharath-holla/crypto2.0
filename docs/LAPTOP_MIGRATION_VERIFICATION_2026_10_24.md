# Laptop migration verification

Date: 24 October 2026, Asia/Calcutta.
Recovery branch: `codex/laptop-migration-20261024`.
Historical base: `b8a574d62213bddab0eca356bdb903ebd4c2973f`.

## Scope

The owner authorized preserving and pushing the existing project for a laptop replacement.
This task preserves the already amended source, regression tests, reports, guide and histories.
It adds migration documentation and exclusions for transient directories. It does not merge the
independent remote hardening/recovery branch or change frozen research methodology/configuration.

The README's example download was corrected from the locked August period to a pre-cutoff June
period. The migration instructions explicitly say not to run acquisition to test a new laptop.
`PROJECT_CONTEXT.md` now points to the latest local remediation rather than allowing the older
handoff's missing-cache description to be mistaken for current implementation status.

Before publication, the staged whitespace check exposed trailing spaces in three historical
Markdown audit reports and intentional Markdown hard-break spaces in the project guide. Only
whitespace formatting was normalized in those text files. Git initially classified the ASCII
encoded PDF as text; `.gitattributes` now marks PDFs binary to prevent Windows line-ending
conversion from corrupting their offsets. The PDF itself was not regenerated or altered; its
staged bytes must match the previously reviewed file exactly.

## Fresh checks on the preserved root source

| Check | Actual result |
| --- | --- |
| Full root pytest suite | **886 passed, 5 skipped, zero failures/errors**, one warning; 506.03 seconds |
| Targeted causal membership, standalone remediation, deep debug and integration guard suites | **135 passed**, zero failures; one warning; 19.12 seconds |
| Ruff lint | PASS on `src tests integration scripts` |
| Ruff formatting | PASS; 252 files already formatted |
| Python compilation | PASS on `src/crypto_ai scripts tests` |
| Dependency lock | PASS offline; 31 packages resolved; no dependency-file changes |
| Git whitespace checks | PASS for root and historical WIP changes; Windows LF/CRLF notices are informational |
| Configuration safety flags | `LOCKED_UNUSED`, used=false and evaluation_authorized=false unchanged |
| Public guide | Existing reviewed 29-page PDF and editable Markdown included |
| Secret-pattern screening | Reviewed source/new docs/scratch scanned without printing values; known existing synthetic fixture/generator matches manually inspected |
| Historical WIP | Secret-pattern and whitespace checks only; **not behaviorally verified or approved for use** |
| Linux gate, real Gold/cache equivalence, GPU, model qualification | **NOT RUN / NOT QUALIFIED** |
| Cloud operations, account/order access, protected-period evaluation | **NONE** |

The five skipped tests are Bash/Linux log-rotation checks. The warning is the known Windows
joblib physical-core discovery fallback. Neither should be called a passing Linux gate.

The first offline lockfile invocation encountered the sandbox's default cache permissions. It
was rerun successfully with a dedicated writable cache, without changing dependencies:

```powershell
uv --cache-dir local_artifacts/laptop-migration-uv-cache-20261024 lock --check --offline
```

The full pytest XML remains private/generated at
`local_artifacts/phase7/verification/laptop-migration-full-20261024.xml`. The sanitized public
manifest records the suite counts, package versions and hashes of the actual staged Git content.
Tests ran on the root scientific working state before its preservation commit; no scientific
source was changed during this migration task. No unit-test run from the older WIP branch is
claimed. The separate application's full build/browser/provider suite was not rerun.

## Preservation boundaries

- Root source: dedicated migration branch, not a forced update or merge into `main`.
- Local `main`: preserve its six existing commits through `4ef91d5`; push fast-forward only.
- Historical dirty worktree: snapshot commit
  `03894edc91f8b19104e13f521a18b2672464d0b8` on
  `codex/laptop-checkpoint-wip-20261024`, including the explicit unverified-WIP warning.
- Independently advanced remote branch: leave `0597a4d` and its ancestors intact; do not push
  the older local branch tip over it or assume those changes are integrated here.
- Existing integration and handoff tags: retain unchanged.
- Scratch: 1,218 screened historical text/source/patch files, 12,040,450 source bytes, saved in a
  private local 3,615,384-byte ZIP. Every archived file was checked against its SHA-256 manifest.
  ZIP SHA-256: `61193c96b6974e60e5a446571de72aaf107278800e0bc409dae50b884c7b7cae`.
- No source, data, cache, cloud resource, or owner scratch file was deleted or reset.

The scratch ZIP is not uploaded. It excludes credentials, market data, databases, environments,
caches, raw logs and opaque archives. Local private environment files, SQLite/WAL state and
ignored research artifacts still require a separate consistent private transfer.

## Publication and clone checks

Before reporting completion, publish the reviewed refs without force, verify their IDs using
`git ls-remote`, and perform a fresh single-branch clone of the migration branch. Compare its
commit and tracked content with the committed snapshot and verify the manifest's Git-content
SHA-256 values. These publication checks occur after this pre-publication record is committed;
their actual IDs/results are reported to the owner and stored in the local post-publication
receipt. A successful commit alone is never proof of a successful GitHub backup.

The final tag identifies the recovery snapshot. A local `git bundle --all` and verified checksum
provide a second offline copy of committed refs, but do not replace data/private-state transfer.
The project remains on hold regardless of publication success.
