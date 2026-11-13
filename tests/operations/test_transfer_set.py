"""ADDED BY CLAUDE (2026-11-13): transfer-set verifier/fetcher, fully offline (mock HTTP)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location(
    "transfer_set", ROOT / "scripts/cloud/transfer_set.py"
)
transfer_set = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer_set)


def test_committed_manifest_is_the_verified_2777_file_set() -> None:
    records = transfer_set.load_manifest()
    assert len(records) == 2777
    assert sum(r["bytes"] for r in records) == 10_998_003_736
    gold = [r for r in records if "/data/gold/" in r["path"]]
    sidecar = [r for r in records if r["path"].startswith("feature_context_sidecar_v3/")]
    assert len(gold) == 139 and len(sidecar) == 140


def _records(payloads: dict[str, bytes]) -> list[dict]:
    return [
        {"path": p, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
        for p, b in payloads.items()
    ]


PAYLOADS = {
    "crypto2-persistent/data/gold/x/part-a.parquet": b"A" * 5000,
    "feature_context_sidecar_v3/part-0001.parquet": b"B" * 777,
}


def _client(served: dict[str, bytes], calls: list) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.split("/o/")[1]
        relative = name.split("/", 1)[1]
        calls.append((relative, request.headers.get("range")))
        assert "authorization" not in {k.lower() for k in request.headers}
        body = served[relative]
        if request.headers.get("range"):
            start = int(request.headers["range"].split("=")[1].rstrip("-"))
            return httpx.Response(206, content=body[start:])
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_dry_run_makes_no_request_and_execute_verifies(tmp_path: Path) -> None:
    records = _records(PAYLOADS)
    calls: list = []
    dry = transfer_set.fetch(
        tmp_path, records, bucket="b", prefix="p", execute=False, client=_client(PAYLOADS, calls)
    )
    assert dry["dry_run"] is True and dry["files_to_fetch"] == 2 and calls == []
    done = transfer_set.fetch(
        tmp_path, records, bucket="b", prefix="p", execute=True, client=_client(PAYLOADS, calls)
    )
    assert done["files_to_fetch"] == 0 and done["fetched"] == 2
    assert transfer_set.verify(tmp_path, records)["status"] == "VERIFIED"
    progress = (tmp_path / ".transfer-state/progress.jsonl").read_text().splitlines()
    assert sum(json.loads(line)["event"] == "VERIFIED" for line in progress) == 2
    calls.clear()
    again = transfer_set.fetch(
        tmp_path, records, bucket="b", prefix="p", execute=True, client=_client(PAYLOADS, calls)
    )
    assert again["fetched"] == 0 and calls == [], "verified files must not be re-downloaded"


def test_fetch_resumes_a_partial_file_with_http_range(tmp_path: Path) -> None:
    records = _records(PAYLOADS)
    first = records[0]
    part = tmp_path / (first["path"] + ".part")
    part.parent.mkdir(parents=True)
    part.write_bytes(PAYLOADS[first["path"]][:1234])
    calls: list = []
    transfer_set.fetch(
        tmp_path, records[:1], bucket="b", prefix="p", execute=True, client=_client(PAYLOADS, calls)
    )
    assert calls == [(first["path"], "bytes=1234-")]
    assert (tmp_path / first["path"]).read_bytes() == PAYLOADS[first["path"]]


def test_corrupt_download_is_discarded_and_never_published(tmp_path: Path) -> None:
    records = _records(PAYLOADS)
    corrupt = {**PAYLOADS, records[1]["path"]: b"X" * 777}
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        transfer_set.fetch(
            tmp_path,
            records[1:],
            bucket="b",
            prefix="p",
            execute=True,
            client=_client(corrupt, []),
            retries=0,
        )
    assert not (tmp_path / records[1]["path"]).exists()
    assert not (tmp_path / (records[1]["path"] + ".part")).exists()


def test_object_urls_use_exact_encoded_names() -> None:
    url = transfer_set.object_url(
        "crypto-ai-data-83921",
        "phase7-transfer-20261113/",
        "crypto2-persistent/data/x=1/a b.parquet",
    )
    assert url == (
        "https://storage.googleapis.com/storage/v1/b/crypto-ai-data-83921/o/"
        "phase7-transfer-20261113%2Fcrypto2-persistent%2Fdata%2Fx%3D1%2Fa%20b.parquet?alt=media"
    )
