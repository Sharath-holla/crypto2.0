from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ALGORITHM = "artifact_fingerprint_v1"


@dataclass(frozen=True, slots=True)
class RootFingerprint:
    root: str
    file_count: int
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ArtifactFingerprint:
    algorithm: str
    roots: tuple[RootFingerprint, ...]
    file_count: int
    byte_count: int
    sha256: str


def _record(relative_path: str, size: int, digest: str) -> bytes:
    return f"{relative_path}\t{size}\t{digest}\n".encode()


def fingerprint_artifacts(repository_root: Path, roots: tuple[Path, ...]) -> ArtifactFingerprint:
    """Hash immutable artifact inventories without reading or writing outside the repository."""

    repository_root = repository_root.resolve()
    root_records: list[tuple[str, list[bytes], int]] = []
    for supplied_root in roots:
        root = (repository_root / supplied_root).resolve()
        if not root.is_relative_to(repository_root):
            raise ValueError(f"artifact root escapes repository: {supplied_root}")
        if not root.is_dir():
            raise FileNotFoundError(root)
        files = sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(repository_root).as_posix(),
        )
        records: list[bytes] = []
        byte_count = 0
        for path in files:
            if path.is_symlink():
                raise ValueError(f"artifact symlink is not canonical: {path}")
            relative = path.relative_to(repository_root).as_posix()
            size = path.stat().st_size
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            records.append(_record(relative, size, digest))
            byte_count += size
        root_records.append((root.relative_to(repository_root).as_posix(), records, byte_count))
    root_records.sort(key=lambda item: item[0])
    roots_result = tuple(
        RootFingerprint(
            root=name,
            file_count=len(records),
            byte_count=byte_count,
            sha256=hashlib.sha256(b"".join(records)).hexdigest(),
        )
        for name, records, byte_count in root_records
    )
    combined_records = [record for _, records, _ in root_records for record in records]
    return ArtifactFingerprint(
        algorithm=ALGORITHM,
        roots=roots_result,
        file_count=sum(item.file_count for item in roots_result),
        byte_count=sum(item.byte_count for item in roots_result),
        sha256=hashlib.sha256(b"".join(combined_records)).hexdigest(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only canonical artifact fingerprint")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--root", action="append", type=Path, required=True)
    args = parser.parse_args()
    result = fingerprint_artifacts(args.repository_root, tuple(args.root))
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
