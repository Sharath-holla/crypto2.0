"""Add-only, manifest-bound install of daily Silver supplement B (folds 1-4, 6-9, 11-14) (stdlib only).

Never overwrites existing input bytes: matching files are reused; a conflicting file is preserved
for audit and the install fails closed. No manifest is edited; no data is generated or downloaded.
"""
import argparse
import hashlib
import json
import os
import tarfile
from datetime import UTC, datetime
from pathlib import Path

ARCHIVE_SHA256 = "afee451735432d3fa30452931690b807db4da8182d7bd01f10e787ca021aa493"
MANIFEST_SHA256 = "5be4e5f1a98a443d4700c9b243dfff8488740d1f8604c7c8b58b7ac608414d13"
FILES, TOTAL_BYTES = 21417, 161396319
PREFIX = "crypto2-persistent/data/phase7/silver/binance/versions/"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True)
    p.add_argument("--inputs", required=True)
    p.add_argument("--audit", required=True)
    p.add_argument("--tag", required=True)
    a = p.parse_args()
    package, inputs, audit = Path(a.package), Path(a.inputs).resolve(), Path(a.audit)
    archive, manifest_path = package / "daily-supplement.tar.gz", package / "manifest.json"
    assert digest(archive.read_bytes()) == ARCHIVE_SHA256, "SUPPLEMENT_ARCHIVE_HASH_MISMATCH"
    assert digest(manifest_path.read_bytes()) == MANIFEST_SHA256, "SUPPLEMENT_MANIFEST_HASH_MISMATCH"
    manifest = json.loads(manifest_path.read_text())
    expected = {r["path"]: r for r in manifest["files"]}
    assert len(expected) == FILES and sum(r["bytes"] for r in expected.values()) == TOTAL_BYTES
    assert not manifest["missing"] and not manifest["mismatch"] and manifest["source_data_changed"] is False
    reused, installed, conflicts = 0, 0, []
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        assert all(m.isfile() for m in members), "SUPPLEMENT_NON_REGULAR_MEMBER"
        assert sorted(m.name for m in members) == sorted(expected), "SUPPLEMENT_MEMBERS_DIFFER_FROM_MANIFEST"
        for member in members:
            rel = Path(member.name)
            assert not rel.is_absolute() and ".." not in rel.parts and member.name.startswith(PREFIX)
            rec = expected[member.name]
            data = tar.extractfile(member).read()
            assert len(data) == rec["bytes"] and digest(data) == rec["sha256"], "SUPPLEMENT_MEMBER_HASH_MISMATCH"
            target = inputs / rel
            assert target.parent.resolve().is_relative_to(inputs) and not target.is_symlink()
            if target.exists():
                current = target.read_bytes()
                if digest(current) == rec["sha256"]:
                    reused += 1
                    continue
                kept = audit / a.tag / rel
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_bytes(current)
                conflicts.append({"path": member.name, "expected_sha256": rec["sha256"], "found_sha256": digest(current), "preserved_at": str(kept)})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name("." + target.name + ".supplement-" + a.tag)
            with tmp.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.link(tmp, target)  # Fails rather than replaces if the path appeared meanwhile.
            tmp.unlink()
            installed += 1
    receipt = {
        "schema": "phase7a_daily_supplement_install_v1",
        "utc": datetime.now(UTC).isoformat(),
        "archive_sha256": ARCHIVE_SHA256,
        "manifest_sha256": MANIFEST_SHA256,
        "inputs": str(inputs),
        "files": FILES,
        "reused": reused,
        "installed": installed,
        "conflicts": conflicts,
    }
    if not conflicts:
        for path, rec in expected.items():
            assert digest((inputs / path).read_bytes()) == rec["sha256"], "POST_INSTALL_HASH_MISMATCH"
        receipt["status"] = "PASS"
    else:
        receipt["status"] = "CONFLICT_FAIL_CLOSED"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / ("install-" + a.tag + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k != "conflicts"} | {"conflict_count": len(conflicts)}), flush=True)
    if conflicts:
        raise SystemExit("SUPPLEMENT_CONFLICT_FAIL_CLOSED")
    print("SUPPLEMENT_VERIFIED", flush=True)


if __name__ == "__main__":
    main()
