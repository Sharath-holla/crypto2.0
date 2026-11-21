"""Owner 2026-11-21: download every model and its evidence from network volume kz9axr9t9v to the Mac.

The kit's collect() mirrored evidence/models/benchmarks/reports of every stage to
/workspace/phase7a-evidence/<pod_id>/<utc>/ before SESSION_COMPLETE, so the volume holds the models of
folds whose Pods stopped before the driver could download them. One short Pod (same EU-SE-1 hosts and
price cap as the driver, covered by the owner's 2026-11-21 $8.40 approval) streams them home and is stopped.
"""
import hashlib
import importlib.util
import json
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("d", "/Users/cortex/.crypto2-transfer/pilot_4fold_20261118.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

DEST = Path("/Users/cortex/Crypto2Results/volume-evidence")
WORK = m.PILOT / ("volume-download-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
EXCLUDE = ("stage-checkpoints", "logs", "linux")


def main():
    assert subprocess.run(["pgrep", "-f", "pilot_4fold_20261118.py"], capture_output=True).returncode != 0, "DRIVER_STILL_RUNNING"
    fleet = m.api.call("POST", "/graphql", {"query": "query { myself { pods { id desiredStatus } } }"})["data"]["myself"]["pods"]
    assert all(p["desiredStatus"] == "EXITED" for p in fleet), "OTHER_RUNNING_POD_PRESENT"
    assert m.wallet() > 1.5, "WALLET_TOO_LOW_FOR_DOWNLOAD_POD"
    WORK.mkdir(mode=0o700)
    DEST.mkdir(parents=True, exist_ok=True)
    state = json.loads((m.PILOT / "pilot-state.json").read_text())
    pod = None
    try:
        pod = m.acquire_pod(state)
        m.trust_host_key(pod, WORK)
        ssh = m.ssh_args(pod, m.KEY)
        ssh[1:1] = ["-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3"]
        for _ in range(20):
            if subprocess.run([*ssh, "test -d /workspace/phase7a-evidence"], capture_output=True, timeout=30).returncode == 0:
                break
            time.sleep(3)
        else:
            raise RuntimeError("VOLUME_EVIDENCE_NOT_REACHABLE")
        excludes = " ".join("--exclude=" + shlex.quote("*/" + e) for e in EXCLUDE)
        size = subprocess.check_output([*ssh, "cd /workspace/phase7a-evidence && du -sh " + excludes + " ."], text=True, timeout=300).strip()
        m.log("VOLUME_EVIDENCE_SIZE " + size)
        for attempt in range(3):
            with (WORK / f"tar-{attempt}.log").open("w") as err:
                tar = subprocess.Popen([*ssh, "cd /workspace/phase7a-evidence && tar -cf - " + excludes + " ."], stdout=subprocess.PIPE, stderr=err)
                untar = subprocess.run(["tar", "-xf", "-", "-C", str(DEST)], stdin=tar.stdout, stderr=err, timeout=5400)
                tar.stdout.close()
                if tar.wait(timeout=60) == 0 and untar.returncode == 0:
                    break
            m.log(f"VOLUME_DOWNLOAD_RETRY attempt={attempt + 1}")
            time.sleep(10)
        else:
            raise RuntimeError("VOLUME_DOWNLOAD_FAILED")
    finally:
        if pod is not None:
            m.stop(m.api, {"pod_id": pod["id"]}, WORK, "VOLUME_DOWNLOAD_DONE")
            for _ in range(40):
                if m.api.call("GET", "/v2/pods/" + pod["id"])["status"] == "EXITED":
                    break
                time.sleep(3)
            m.log("POD_EXITED " + pod["id"])
    # Match every downloaded model.joblib to the SHA its own train-result recorded.
    summary = {}
    for result in sorted(DEST.glob("*/*/evidence/train-result.json")):
        report = json.loads(result.read_text())["reports"][0]
        snapshot = result.parent.parent
        models = list(snapshot.glob("benchmarks/**/model.joblib"))
        digests = {str(p.relative_to(DEST)): hashlib.sha256(p.read_bytes()).hexdigest() for p in models}
        match = [k for k, v in digests.items() if v == report["model_artifact_sha256"]]
        summary.setdefault(report["fold_id"], []).append({"snapshot": str(snapshot.relative_to(DEST)), "model_sha256": report["model_artifact_sha256"], "model_file": match[0] if match else None})
    m.write(DEST / "MODEL_INDEX.json", summary)
    for fold, entries in sorted(summary.items()):
        m.log(f"VOLUME_MODEL {fold} " + ", ".join(f"{e['model_sha256'][:12]} {'OK' if e['model_file'] else 'MISSING'}" for e in entries))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    sys.exit(main())
