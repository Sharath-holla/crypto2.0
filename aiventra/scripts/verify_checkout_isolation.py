"""GitHub GET fixtures + actual Docker broker execution; never executes source on this host."""

import asyncio
import base64
import hashlib
import json
import os
import sys
from uuid import uuid4

import httpx
from company_os import runner_checkout as checkout
from company_os import runner_service as runner
from company_os.config import settings
from company_os.publication import GitHub

MARKER = runner.ROOT / "checkout-verification.json"
SOURCE = """import os, pathlib, socket, unittest
class CheckoutIsolation(unittest.TestCase):
    def test_restricted_snapshot(self):
        self.assertEqual(os.getuid(), 10001)
        for key in ('RUNNER_TOKEN','AIVENTRA_GITHUB_TOKEN','TEST_CHECKOUT_READER','DATABASE_URL','OPENAI_API_KEY'):
            self.assertNotIn(key, os.environ)
        self.assertFalse(pathlib.Path('/var/run/docker.sock').exists())
        self.assertFalse(pathlib.Path('/app/.env').exists())
        self.assertFalse(pathlib.Path('/input/.git').exists())
        with self.assertRaises(OSError): socket.create_connection(('1.1.1.1',80), timeout=0.5)
        with self.assertRaises(OSError): pathlib.Path('/input/changed').write_text('x')
"""


async def verify():
    settings().github_publication_repositories = "fixture/checkout-isolation"
    settings().github_publication_token_env = "TEST_CHECKOUT_READER"
    os.environ["TEST_CHECKOUT_READER"] = "deterministic-transport-fixture-only"
    raw = SOURCE.encode()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    reads = []

    async def read(self, method, path, body=None, missing=False):
        assert method == "GET" and body is None
        reads.append(path)
        if path.startswith("git/ref/"):
            return {"object": {"sha": "a" * 40}}
        if path.startswith("git/commits/"):
            return {"tree": {"sha": "b" * 40}}
        if path.startswith("git/trees/"):
            return {
                "tree": [
                    {
                        "path": "test_checkout.py",
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob,
                        "size": len(raw),
                    }
                ]
            }
        return {"encoding": "base64", "content": base64.b64encode(raw).decode()}

    # Only this trusted verification process is patched. No fixture endpoint/switch in production.
    GitHub.request = read
    request = checkout.CheckoutInput(
        job_id=uuid4(),
        org_id=uuid4(),
        project_id=uuid4(),
        repository="fixture/checkout-isolation",
        branch="main",
        commit="a" * 40,
    ).model_dump(mode="json")
    headers = {"Authorization": "Bearer " + os.environ["RUNNER_TOKEN"]}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=runner.app), base_url="http://broker", headers=headers, timeout=150
    ) as client:
        value = (await client.post("/checkouts", json=request)).json()
        assert value["status"] == "ready", value
        assert not (runner.ROOT / "results" / (request["job_id"] + ".json")).exists(), (
            "Acquisition executed code"
        )
        assert (await client.post("/checkouts", json=request)).json() == value and len(reads) == 4
        scope = {key: request[key] for key in ("org_id", "project_id")}
        assert (
            await client.get(f"/checkouts/{request['job_id']}", params={**scope, "project_id": str(uuid4())})
        ).status_code == 404
        execution = str(uuid4())
        result = (
            await client.post(
                f"/checkouts/{request['job_id']}/execute",
                json={**scope, "job_id": execution, "suite": "python-unittest", "timeout": 30},
            )
        ).json()
        assert result["status"] == "completed" and result["exit_code"] == result["build"]["exit_code"] == 0, (
            result
        )
        assert "Ran 1 test" in result["logs"] and "dedicated Docker" in result["environment"]
        assert result["policy"]["network"] == "none"
        MARKER.write_text(json.dumps({**scope, "checkout": request["job_id"], "execution": execution}))
    print(
        "GitHub GET fixture checkout and real Docker source isolation/build/test verified; no live GitHub checkout claimed."
    )


def snapshot():
    marker = json.loads(MARKER.read_text())
    value = checkout.get(runner.ROOT, marker["checkout"], marker["org_id"], marker["project_id"])
    assert value["status"] == "ready" and checkout.files(runner.ROOT, value)["test_checkout.py"] == SOURCE
    result = json.loads((runner.ROOT / "results" / (marker["execution"] + ".json")).read_text())
    assert result["exit_code"] == 0
    print(
        json.dumps(
            {
                "checkout": value["job_id"],
                "commit": value["commit"],
                "digest": value["source_digest"],
                "execution": marker["execution"],
                "result_digest": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
                "source": "GitHub GET transport fixture",
                "execution_verified": "actual restricted Docker",
            },
            sort_keys=True,
        )
    )


if "--snapshot" in sys.argv:
    snapshot()
else:
    asyncio.run(verify())
