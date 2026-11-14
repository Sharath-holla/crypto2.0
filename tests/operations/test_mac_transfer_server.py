"""ADDED BY CLAUDE (2026-11-14): security and resume behaviour of the Mac transfer server.

The real server runs on 127.0.0.1 with throw-away files; the real fetcher downloads from it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import threading
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/cloud/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server_module = _load("mac_transfer_server")
transfer_set = _load("transfer_set")

FILES = {
    "crypto2-persistent/data/gold/symbol=BTCUSDT/year=2020/part-a.parquet": os.urandom(300_000),
    "feature_context_sidecar_v3/SIDECAR_COMPLETE": b"complete\n",
}


@pytest.fixture
def running(tmp_path: Path):
    root = tmp_path / "stage"
    for relative, body in FILES.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(body)
    (root / "crypto2-persistent/secret-not-in-manifest.txt").write_bytes(b"private")
    records = [
        {"path": p, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
        for p, b in FILES.items()
    ]
    holder: dict = {}
    ready = threading.Event()

    def on_ready(server, state):
        holder.update(server=server, state=state)
        ready.set()

    def run(ttl: float = 5, failures: int = 5):
        thread = threading.Thread(
            target=server_module.serve,
            args=(root,),
            kwargs={
                "port": 0,
                "ttl_minutes": ttl,
                "allow": None,
                "verify_sha": True,
                "token_file": tmp_path / "secret/token",
                "log_file": tmp_path / "access.log",
                "max_failures": failures,
                "records": records,
                "ready": on_ready,
            },
            daemon=True,
        )
        thread.start()
        assert ready.wait(10)
        port = holder["server"].server_address[1]
        token = (tmp_path / "secret/token").read_text()
        return thread, f"http://127.0.0.1:{port}", token

    yield {"run": run, "records": records, "tmp": tmp_path, "holder": holder}
    if "server" in holder:
        holder["server"].shutdown()


def test_every_request_needs_the_token_and_nothing_else_is_served(running) -> None:
    _thread, base, token = running["run"]()
    path = next(iter(FILES))
    url = f"{base}/files/{path}"
    assert httpx.get(url).status_code == 401
    assert httpx.get(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    auth = {"Authorization": f"Bearer {token}"}
    for probe in (
        "/",
        "/files/",
        "/files",
        "/files/crypto2-persistent/",
        "/files/crypto2-persistent/secret-not-in-manifest.txt",
        "/files/../../etc/passwd",
        "/files/%2e%2e/%2e%2e/etc/passwd",
    ):
        assert httpx.get(base + probe, headers=auth).status_code == 404, probe
    assert httpx.post(url, headers=auth).status_code == 405
    response = httpx.get(url, headers=auth)
    assert response.status_code == 200 and response.content == FILES[path]
    assert response.headers["x-content-sha256"] == hashlib.sha256(FILES[path]).hexdigest()
    assert response.headers["cache-control"] == "no-store, private"
    assert httpx.get(f"{base}/healthz", headers=auth).json()["files"] == 2


def test_token_file_is_private_and_never_logged(running) -> None:
    _thread, base, token = running["run"]()
    mode = stat.S_IMODE(os.stat(running["tmp"] / "secret/token").st_mode)
    assert mode == 0o600
    httpx.get(f"{base}/files/{next(iter(FILES))}", headers={"Authorization": f"Bearer {token}"})
    assert token not in (running["tmp"] / "access.log").read_text()


def test_http_ranges(running) -> None:
    _thread, base, token = running["run"]()
    path = next(iter(FILES))
    auth = {"Authorization": f"Bearer {token}"}
    part = httpx.get(f"{base}/files/{path}", headers={**auth, "Range": "bytes=100-199"})
    assert part.status_code == 206 and part.content == FILES[path][100:200]
    tail = httpx.get(f"{base}/files/{path}", headers={**auth, "Range": "bytes=299990-"})
    assert tail.content == FILES[path][299990:]
    bad = httpx.get(f"{base}/files/{path}", headers={**auth, "Range": "bytes=999999-"})
    assert bad.status_code == 416


def test_repeated_auth_failures_stop_the_server(running) -> None:
    thread, base, _token = running["run"](failures=3)
    for _ in range(3):
        httpx.get(f"{base}/healthz", headers={"Authorization": "Bearer guess"})
    thread.join(5)
    assert not thread.is_alive()
    assert not (running["tmp"] / "secret/token").exists(), "token file removed on stop"


def test_server_expires(running) -> None:
    thread, base, token = running["run"](ttl=0.02)  # 1.2 s
    time.sleep(1.5)
    thread.join(5)
    assert not thread.is_alive()
    with pytest.raises(httpx.HTTPError):
        httpx.get(f"{base}/healthz", headers={"Authorization": f"Bearer {token}"}, timeout=2)


def test_fetcher_downloads_resumes_and_verifies_through_the_server(running, tmp_path) -> None:
    _thread, base, token = running["run"]()
    records = running["records"]
    destination = tmp_path / "vm-staging"
    first = records[0]
    partial = destination / (first["path"] + ".part")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(FILES[first["path"]][:12345])
    client = httpx.Client(headers={"Authorization": f"Bearer {token}"})
    result = transfer_set.fetch(destination, records, base_url=base, execute=True, client=client)
    assert result["fetched"] == 2 and result["throughput_mb_per_s"] > 0
    assert transfer_set.verify(destination, records)["status"] == "VERIFIED"
    log = (running["tmp"] / "access.log").read_text()
    assert " 206 " in log, "the partial file must resume with an HTTP range"
    again = transfer_set.fetch(destination, records, base_url=base, execute=True, client=client)
    assert again["fetched"] == 0


def test_batch_selection_rejects_paths_outside_the_manifest() -> None:
    records = transfer_set.load_manifest()
    chosen = transfer_set.select(records, ["feature_context_sidecar_v3/SIDECAR_COMPLETE"])
    assert len(chosen) == 1
    with pytest.raises(SystemExit, match="NOT_IN_MANIFEST"):
        transfer_set.select(records, ["../../etc/passwd"])
