"""Actual Docker probes. Run inside the trusted broker; never run fixture code on its host."""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path("/jobs")
URL = os.environ.get("RUNNER_URL", "http://localhost:8090")
HEADERS = {"Authorization": "Bearer " + os.environ["RUNNER_TOKEN"]}

PROBE = """import os, pathlib, socket, unittest
class Isolation(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(os.getuid(), 10001)
        for key in ('RUNNER_TOKEN','JWT_SECRET','OWNER_PASSWORD','DATABASE_URL','OPENAI_API_KEY','PROVIDER_SECRET_KEY','DOCKER_HOST'):
            self.assertNotIn(key, os.environ)
        self.assertFalse(pathlib.Path('/var/run/docker.sock').exists())
        self.assertFalse(pathlib.Path('/app/.env').exists())
        if pathlib.Path('/opt/aiventra/quality_runner.py').exists():
            with self.assertRaises(OSError): pathlib.Path('/opt/aiventra/quality_runner.py').write_text('tamper')
        status = pathlib.Path('/proc/self/status').read_text()
        self.assertIn('CapEff:\\t0000000000000000', status)
        with self.assertRaises(OSError): pathlib.Path('/etc/forbidden').write_text('x')
        with self.assertRaises(OSError): pathlib.Path('/input/forbidden').write_text('x')
        with self.assertRaises(OSError): socket.create_connection(('1.1.1.1', 80), timeout=0.5)
        pathlib.Path('/workspace/ephemeral').write_text('allowed ephemeral workspace')
        pathlib.Path('/tmp/ephemeral').write_text('allowed bounded temporary file')
        self.assertEqual(pathlib.Path('/sys/fs/cgroup/pids.max').read_text().strip(), '128')
        self.assertEqual(pathlib.Path('/sys/fs/cgroup/memory.max').read_text().strip(), '536870912')
"""


async def verify():
    ids = []
    async with httpx.AsyncClient(base_url=URL, headers=HEADERS, timeout=150, trust_env=False) as client:
        assert (
            await client.post("/run", headers={"Authorization": "Bearer invalid"}, json={})
        ).status_code == 401

        async def run(files, suite="python-unittest", timeout=20):
            job_id = str(uuid4())
            response = await client.post(
                "/run", json={"job_id": job_id, "suite": suite, "files": files, "timeout": timeout}
            )
            assert response.status_code == 200, f"Runner request failed: {response.status_code}"
            value = response.json()
            ids.append(job_id)
            assert value["status"] == "completed", value.get("logs")
            return value

        python = await run({"test_isolation.py": PROBE})
        assert python["exit_code"] == 0 and "Ran 1 test" in python["logs"], python["logs"]
        assert python["build"]["exit_code"] == 0
        policy = python["policy"]
        assert policy["network"] == "none" and policy["read_only_root"]
        assert policy["user"] == "10001:10001" and policy["cap_drop"] == ["ALL"]
        assert policy["memory"] == 536870912 and policy["pids"] == 128 and policy["cpu_nano"] == 1000000000
        assert "/input" in policy["mount_destinations"] and set(policy["mount_destinations"]).issubset(
            {"/input", "/tmp", "/workspace"}
        )
        quality = await run(
            {
                "aiventra_qa/__init__.py": "",
                "aiventra_qa/round_3/__init__.py": "",
                "aiventra_qa/round_3/test_isolation.py": PROBE,
            },
            "python-qa-3",
        )
        assert quality["exit_code"] == quality["build"]["exit_code"] == 0, quality
        assert '"status": "PASS"' in quality["logs"] and "AIVENTRA_QA_RESULT=" in quality["logs"]
        assert len(quality["request_hash"]) == 64 and quality["policy"]["image_id"]
        assert {k: v for k, v in quality["policy"].items() if k != "image_id"} == {
            k: v for k, v in policy.items() if k != "image_id"
        }
        quality_broken = await run({"test_broken.py": "def invalid(:\n"}, "python-qa-1")
        assert quality_broken["build"]["exit_code"] != 0
        assert quality_broken["command"] == quality_broken["build"]["command"]
        node = await run(
            {
                "sum.test.js": "const test=require('node:test'),assert=require('node:assert/strict');test('real node regression',()=>assert.equal(2+3,5));"
            },
            "node-test",
        )
        assert node["exit_code"] == 0 and "# tests 1" in node["logs"] and node["build"]["exit_code"] == 0
        broken = await run({"test_broken.py": "def invalid(:\n"})
        assert broken["build"]["exit_code"] != 0
        timed = await run({"test_slow.py": "import time\ntime.sleep(30)\n"}, timeout=2)
        assert timed["exit_code"] == 124
        flooded = await run(
            {"test_flood.py": "for i in range(20000):\n print('x'*1000, flush=True)\n"}, timeout=10
        )
        assert flooded["exit_code"] == 124 and len(flooded["logs"].encode()) <= 500100
        invalid = await client.post(
            "/run",
            json={"job_id": str(uuid4()), "suite": "python-unittest", "files": {"../escape.py": "bad"}},
        )
        assert invalid.status_code == 422
        command = await client.post(
            "/run", json={"job_id": str(uuid4()), "suite": "shell", "files": {"x": "x"}, "command": ["sh"]}
        )
        assert command.status_code == 422
        cancelled_id = str(uuid4())
        pending = asyncio.create_task(
            client.post(
                "/run",
                json={
                    "job_id": cancelled_id,
                    "suite": "python-unittest",
                    "files": {"test_slow.py": "import time\ntime.sleep(30)\n"},
                    "timeout": 40,
                },
            )
        )
        for _ in range(30):
            await asyncio.sleep(0.2)
            response = await client.get(f"/jobs/{cancelled_id}")
            if response.status_code == 200:
                break
        duplicate = await client.post(
            "/run", json={"job_id": cancelled_id, "suite": "python-unittest", "files": {"other.py": "pass"}}
        )
        assert duplicate.status_code == 409
        assert (await client.post(f"/jobs/{cancelled_id}/cancel")).status_code == 200
        cancelled = (await pending).json()
        assert cancelled["exit_code"] == 125
        ids.append(cancelled_id)
        async with httpx.AsyncClient(base_url=os.environ["RUNNER_DAEMON_URL"], trust_env=False) as daemon:
            containers = await daemon.get(
                "/containers/json",
                params={"all": "true", "filters": json.dumps({"label": ["aiventra.runner=restricted-v1"]})},
            )
            assert containers.status_code == 200 and containers.json() == [], "Generated containers leaked"
    (ROOT / "verification.json").write_text(json.dumps(ids))
    print(
        "Actual Docker: Python/Node builds and nonempty tests; UID/caps/filesystem/network/secrets/cgroup limits; invalid paths/commands; timeout/output/cancellation/duplicate cleanup passed"
    )


def snapshot():
    ids = json.loads((ROOT / "verification.json").read_text())
    values = [(ROOT / "results" / (job_id + ".json")).read_bytes() for job_id in ids]
    assert len(values) == 8
    print(
        json.dumps(
            {"runner_results": len(values), "sha256": hashlib.sha256(b"".join(values)).hexdigest()},
            sort_keys=True,
        )
    )


async def interrupted(check=False):
    """Actual broker interruption; generated slow test executes only in Docker."""
    from company_os.runner_protocol import RunInput, request_digest

    checkpoint = ROOT / "qa-interrupted-verification.json"
    if check:
        saved = json.loads(checkpoint.read_text())
        data = RunInput.model_validate(saved["request"])
    else:
        data = RunInput(
            job_id=uuid4(),
            suite="python-qa-3",
            files={
                "aiventra_qa/__init__.py": "",
                "aiventra_qa/round_3/__init__.py": "",
                "aiventra_qa/round_3/test_wait.py": "import time\nimport unittest\nclass Slow(unittest.TestCase):\n def test_wait(self):\n  time.sleep(90)\n",
            },
        )
    job_id = str(data.job_id)
    async with (
        httpx.AsyncClient(base_url=URL, headers=HEADERS, timeout=140, trust_env=False) as client,
        httpx.AsyncClient(base_url=os.environ["RUNNER_DAEMON_URL"], trust_env=False) as daemon,
    ):
        filters = {"all": "true", "filters": json.dumps({"label": [f"aiventra.job={job_id}"]})}
        if check:
            value = (await client.get(f"/jobs/{job_id}")).json()
            assert value["status"] == "interrupted" and value["exit_code"] == 125, value
            assert value["request_hash"] == request_digest(data)
            assert (await client.post("/run", json=data.model_dump(mode="json"))).status_code == 409
            assert (await client.get(f"/jobs/{job_id}")).json() == value
            containers = await daemon.get("/containers/json", params=filters)
            assert containers.status_code == 200 and containers.json() == []
            assert not (ROOT / job_id).exists(), "Interrupted input staging leaked"
            print(
                json.dumps(
                    {"actual_qa_broker_restart": "passed", "job_id": job_id, "duplicate_dispatch": False}
                )
            )
            return
        pending = asyncio.create_task(client.post("/run", json=data.model_dump(mode="json")))
        try:
            for _ in range(100):
                containers = await daemon.get("/containers/json", params=filters)
                containers.raise_for_status()
                if any(
                    c["State"] == "running" and any(n.endswith("-test") for n in c["Names"])
                    for c in containers.json()
                ):
                    value = (await client.get(f"/jobs/{job_id}")).json()
                    assert value["status"] == "running" and value["request_hash"] == request_digest(data)
                    checkpoint.write_text(json.dumps({"request": data.model_dump(mode="json")}))
                    print(json.dumps({"actual_qa_job_running": job_id}))
                    return
                await asyncio.sleep(0.2)
            raise AssertionError("Actual restricted QA test container did not start")
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
    elif "--start-interrupted" in sys.argv or "--check-interrupted" in sys.argv:
        asyncio.run(interrupted(check="--check-interrupted" in sys.argv))
    else:
        asyncio.run(verify())
