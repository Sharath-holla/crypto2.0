"""ADDED BY CLAUDE (2026-11-13): private GCS result persistence, offline (mock HTTP)."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from crypto_ai.phase7 import run_persistence

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("gcs_results", ROOT / "scripts/cloud/gcs_results.py")
gcs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gcs)


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.startswith("/upload/"):
                assert request.url.params["ifGenerationMatch"] == "0"
                name = request.url.params["name"]
                if name in self.objects:
                    return httpx.Response(412)
                self.objects[name] = request.content
                return httpx.Response(200, json=self._meta(name))
            name = request.url.path.split("/o/", 1)[1]
            name = httpx.URL("http://x/" + name).path[1:]
            if name not in self.objects:
                return httpx.Response(404)
            if request.url.params.get("alt") == "media":
                return httpx.Response(200, content=self.objects[name])
            return httpx.Response(200, json=self._meta(name))

        return httpx.Client(transport=httpx.MockTransport(handler))

    def _meta(self, name: str) -> dict:
        digest = base64.b64encode(hashlib.md5(self.objects[name]).digest()).decode()
        return {"name": name, "md5Hash": digest}


def _exported(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "report").mkdir(parents=True)
    (run / "report/report.json").write_text(json.dumps({"status": "COMPLETE"}))
    (run / "model.joblib").write_bytes(b"model")
    destination = tmp_path / "persisted"
    run_persistence.export({"out": run}, destination, metadata={}, execute=True)
    return destination


def test_push_is_create_only_verified_and_pull_round_trips(tmp_path: Path) -> None:
    source = _exported(tmp_path)
    bucket = FakeBucket()
    dry = gcs.push(
        source, bucket="b", prefix="phase7-results/r1", execute=False, client=bucket.client()
    )
    assert dry["dry_run"] is True and bucket.objects == {}
    done = gcs.push(
        source, bucket="b", prefix="phase7-results/r1", execute=True, client=bucket.client()
    )
    assert done["verified_objects"] == 3 and len(bucket.objects) == 3
    again = gcs.push(
        source, bucket="b", prefix="phase7-results/r1", execute=True, client=bucket.client()
    )
    assert again["pre_existing_identical"] == 3, "existing objects are never overwritten"
    pulled = gcs.pull(
        bucket="b",
        prefix="phase7-results/r1",
        destination=tmp_path / "pulled",
        execute=True,
        client=bucket.client(),
    )
    assert pulled["objects"] == 3
    assert (tmp_path / "pulled/out/model.joblib").read_bytes() == b"model"


def test_push_refuses_when_remote_object_differs(tmp_path: Path) -> None:
    source = _exported(tmp_path)
    bucket = FakeBucket()
    bucket.objects["phase7-results/r1/out/model.joblib"] = b"something else"
    with pytest.raises(RuntimeError, match="REMOTE_OBJECT_DIFFERS"):
        gcs.push(
            source, bucket="b", prefix="phase7-results/r1", execute=True, client=bucket.client()
        )
