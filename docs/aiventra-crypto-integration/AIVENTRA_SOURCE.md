# Aiventra source provenance

- Source URL: https://github.com/Sharath-holla/Aiventra.git
- Source/default branch: `master`.
- Source commit: `1d8b479d48a4f208529d71f0cd355853a9288776`.
- Import date: 2026-10-13.
- Source tracked archive exported at: `2026-10-13T12:39:34Z`.
- Source archive SHA-256: `8be2ff92c9a791915c9756031e7082e68894803f51cae1435c30206e717d6696`.
- Import method: shallow read-only acquisition outside Crypto, `git archive HEAD`,
  tracked-file export into `aiventra/` on `integration/aiventra-crypto-os`.
- Files: 386 tracked upstream files initially imported byte-for-byte.
- Intentionally excluded: `.git` (not a tracked file), runtime/private/generated files,
  dependencies and databases (none supplied by the tracked archive). No tracked file omitted.
- License/NOTICE: neither present in this source snapshot. No open-source license inferred.
  Existing attribution and copyright text preserved; owner's explicit integration request
  is the authority for this work, not a grant of additional third-party licensing rights.
- Initial source token/private-key scanner: 386 blobs, zero findings; no secret values printed.
- Local changes: focused API router/domain client, Crypto dashboard/navigation,
  protected integration-record handling and integration verification described in the final
  report. All other source and upstream records are retained, not rebuilt.
- No nested Git repository, submodule or Aiventra remote. No upstream edits, branches or pushes.
- Crypto source branch/head retained:
  `phase7a-pre-lightning-hardening-20261003` / `24dd8148af8cc1db4827dd40d2754d5ec1846ee6`.

Upstream status documents report their own historical results. They do not certify this
imported integration, the local Windows environment, or current Crypto data/lineage.

Reproducible read-only comparison: `python -m integration.crypto_aiventra.verify_source
--source-archive <original-source.tar>`. It reports original tracked SHA-256 values,
missing tracked files, local modifications and nested Git presence without changing
either repository. The initial import retained all 386 tracked files; the verified
working copy has zero missing tracked files and only the focused local changes listed
in the final report. Private/runtime/generated files are not part of this source archive.
