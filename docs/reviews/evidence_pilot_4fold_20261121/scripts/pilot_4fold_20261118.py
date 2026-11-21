"""Predeclared 4-fold pilot (folds 0, 5, 10, 15) for architecture-G0-A6-60m-raw.

One fold per Pod session: acquire Pod -> verify host key via trusted RunPod gateway -> fold-bound
contract -> arm outside-Pod stop controller -> upload frozen source 0034184 + kit opsfix8 -> all gates
-> prepare/reload/probe/train with fold-bound approvals -> provider stop. Any failure stops compute and
aborts the pilot. Shared pilot budget: one session start, wallet origin, cap and deadline for all folds.
"""

import base64
import hashlib
import http.client
import json
import math
import os
import plistlib
import re
import shlex
import subprocess
import sys
import time
import tempfile
import traceback
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

KIT = Path("/Users/cortex/.crypto2-transfer/operator-opsfix8/crypto2-operator-kit")
sys.path.insert(0, str(KIT / "scripts/closure"))
from runpod_phase7_ops import CANONICAL_FOLDS, contract, write  # noqa: E402
from runpod_stop_controller_phase7 import API, pod_binding, ssh_args, stop  # noqa: E402
from runpod_wallet_policy_phase7 import decision  # noqa: E402

PILOT = Path("/Users/cortex/.crypto2-transfer/phase7-pilot-4fold-20261118")
BASE = Path("/Users/cortex/Crypto2Data/reports/phase7-constrained-20261117")
SOURCE = ("crypto2-source-0034184cdf9f.tar.gz", "ce85ab2754bd176b9a5eb2d010e9caf6b95b4f5b1d8db00dc58e865fef32aa5b")
KIT_ARCHIVE = (
    "crypto2-constrained-operator-kit-0034184cdf9f-opsfix8.tar.gz",
    "2b29e638da495f882e86d03686a1965b8fe39463dcce56c9f55d53ee3fbe4fc7",
)
KEY = "/Users/cortex/.ssh/runpod_crypto2"
# 2026-11-20 resume: fresh owner contract in its own file; the 18 Nov contract and stop sentinel stay untouched.
SESSION_PATH = PILOT / "pilot-session-20261121e.json"
AUTHORIZATION_PATH = PILOT / "OWNER_AUTHORIZATION_20261121e.json"
AUTHORIZATION_NOTE = "2026-11-21 owner (Sharath): APPROVED. TRAIN ALL REMAINING FOLDS, EU-SE-1; SPEND UP TO $8.40 (WALLET FLOOR $1); 8-HOUR WINDOW."
SUPPLEMENT_DIR = BASE / "pilot-daily-supplement-20261118"
SUPPLEMENT_FILES = (
    ("daily-supplement.tar.gz", "13a236798ea8069f5dc87b1fcd4629b9fff90a41ee9d900b8f62982f18edebcf"),
    ("manifest.json", "19c081c90999d35a58c1ac76d90fc3f121854a605af987e16d7b86ede3852513"),
)
SUPPLEMENT_APPLY = (Path("/Users/cortex/.crypto2-transfer/apply_pilot_daily_supplement_20261119.py"), "dd47fdf43d940ece530d0ba2f0ba28d8d4ea436b92e4f6722edbd4d07fb33fcb")
# 2026-11-21: the transfer covered Fold 0 only; supplement A adds folds 5/10/15, supplement B the other 12 folds.
SUPPLEMENTS = (
    (SUPPLEMENT_DIR, SUPPLEMENT_FILES, SUPPLEMENT_APPLY, "/workspace/phase7a-supplements/daily-20261118-13a236798ea8"),
    (
        BASE / "pilot-daily-supplement-20261121",
        (
            ("daily-supplement.tar.gz", "afee451735432d3fa30452931690b807db4da8182d7bd01f10e787ca021aa493"),
            ("manifest.json", "5be4e5f1a98a443d4700c9b243dfff8488740d1f8604c7c8b58b7ac608414d13"),
        ),
        (Path("/Users/cortex/.crypto2-transfer/apply_pilot_daily_supplement_20261121.py"), "5fbc2c98ec215c67bbef22a3bcacacde2677b1486e49ea75f4950e082dbef54c"),
        "/workspace/phase7a-supplements/daily-20261121-afee45173543",
    ),
)
FOLDS = tuple(range(16))  # 2026-11-21: owner extended the pilot to all 16 canonical folds
OPERATOR_TESTS = "68 passed"
RESUME_TAG = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
LOCAL_ROOT = None
MODEL_DOWNLOADS = Path("/Users/cortex/Crypto2Results/models")
PILOT_CAP_USD = 8.40
PILOT_HOURS = 8.0
MAX_COMPUTE_USD_PER_HOUR = 1.40
ALL_IN_UPPER_USD_PER_HOUR = 1.70
# Hosts able to meet constrained_48gb (>= 48 GiB RAM, >= 8 effective CPUs), cheapest suitable first
# within each class; bootstrap measures the real allocation and fails closed.
HOSTS = (('NVIDIA A40', 2, 49, 8), ('NVIDIA RTX A6000', 2, 49, 8), ('NVIDIA RTX A5000', 2, 25, 5), ('NVIDIA RTX 4000 Ada Generation', 2, 25, 5), ('NVIDIA RTX A4000', 2, 25, 5), ('NVIDIA RTX A5000', 3, 17, 4), ('NVIDIA A40', 1, 49, 10))
POD_LOCAL_REGIONS = ["EU-RO-1", "EU-CZ-1", "US-NC-1"]
TRANSFER_DEFINITION = Path("/Users/cortex/Projects/crypto2.0/docs/runpod/transfer.expected.json")

STAGES = ("bootstrap", "operator-tests", "verify-transfer", "preflight", "prepare", "reload", "memory-probe", "train")


class DeployAPI(API):
    def call(self, method, path, data=None):
        read_only = method == "GET" or (method == "POST" and path == "/graphql" and isinstance(data, dict) and str(data.get("query", "")).lstrip().startswith("query"))
        attempts = 3 if read_only else 1
        for attempt in range(attempts):
            with tempfile.TemporaryDirectory(prefix="crypto2-api-") as td:
                root=Path(td);cfg=root/"curl.cfg"
                assert re.fullmatch("[A-Za-z0-9_-]+", self.key)
                cfg.write_text('header = "Authorization: Bearer '+self.key+'"\nheader = "Content-Type: application/json"\n');cfg.chmod(0o600)
                response=root/"response.json"
                argv=["curl","-4","--http1.1","--silent","--show-error","--connect-timeout","10","--max-time","30","--config",str(cfg),"--request",method,"--output",str(response),"--write-out","%{http_code}"]
                if data is not None:
                    payload=root/"body.json";payload.write_text(json.dumps(data));argv.extend(["--data-binary","@"+str(payload)])
                argv.append("https://api.runpod.io"+path)
                result=subprocess.run(argv,capture_output=True,text=True,timeout=35)
                code=int(result.stdout or 0)
                if result.returncode:
                    if read_only and attempt+1<attempts:
                        time.sleep(2);continue
                    raise TimeoutError("CURL_API_TRANSPORT_UNCERTAIN" if not read_only else "CURL_API_READ_UNAVAILABLE")
                if code>=400:
                    if read_only and code in {429,502,503,504} and attempt+1<attempts:
                        time.sleep(2);continue
                    raise RuntimeError("RUNPOD_API_HTTP_"+str(code))
                raw=response.read_text()
                return json.loads(raw) if raw else {}

    def create(self,payload):
        return self.call("POST","/v2/pods",payload)


api = DeployAPI("~/.crypto2-transfer/runpod-api-key")


def log(message):
    line = datetime.now(UTC).isoformat() + " " + message
    print(line, flush=True)
    with (PILOT / "pilot.log").open("a") as f:
        f.write(line + "\n")


def wallet():
    return float(api.call("POST", "/graphql", {"query": "query { myself { clientBalance currentSpendPerHr } }"})["data"]["myself"]["clientBalance"])


def pilot_session():
    path = SESSION_PATH
    if path.exists():
        return json.loads(path.read_text())
    raise RuntimeError("EXISTING_SHARED_PILOT_CONTRACT_REQUIRED; NEVER_RESET_BUDGET_ON_RESUME")


# Owner 2026-11-19: restart only this existing Pod; never create a new Pod or volume.
REUSE_POD_ID = None  # 2026-11-19 later: owner approved a new Pod outside EU-SE-1


def acquire_pod(state):
    pod_id = REUSE_POD_ID
    if pod_id:
        pod = api.call("GET", "/v2/pods/" + pod_id)
        assert pod["status"] == "EXITED", "PILOT_POD_NOT_EXITED"
        state["pod_id"] = pod_id
        write(PILOT / "pilot-state.json", state)
        try:
            api.call("POST", "/v2/pods/" + pod_id + "/action", {"action": "start"})
            log("RESTARTED " + pod_id)
        except RuntimeError as exc:
            log("RESTART_REFUSED " + str(exc) + "; owner forbids new Pods")
            raise RuntimeError("REUSE_POD_RESTART_REFUSED") from None
    if not pod_id:
        fleet = api.call("POST", "/graphql", {"query": "query { myself { pods { id desiredStatus } } }"})["data"]["myself"]["pods"]
        assert all(p["desiredStatus"] == "EXITED" for p in fleet), "OTHER_RUNNING_POD_PRESENT"
        public = Path(KEY + ".pub").read_text().strip()
        for gpu, count, ram, vcpu in HOSTS:
            # The live create response supplies the price; do not depend on the unavailable catalog.
            versions = ['13.2']
            payload = {
                "name": "crypto2-p7a-pilot-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
                "image": "runpod/base:1.0.2-ubuntu2404",
                "gpu": {"id": gpu, "count": count, "minRamPerGpu": ram, "minVcpuCountPerGpu": vcpu, **({"allowedCudaVersions": versions} if versions else {})},
                "dataCenterIds": ["EU-SE-1"],
                "disk": 200,
                "mounts": {"network": [{"volumeId": "kz9axr9t9v", "path": "/workspace"}]},
                "ports": ["22/tcp"],
                "startSsh": True,
                "env": {"PUBLIC_KEY": public},
            }
            try:
                state["pending_create_name"] = payload["name"]
                write(PILOT / "pilot-state.json", state)
                try:
                    created = api.create(payload)
                except (TimeoutError, urllib.error.URLError, http.client.RemoteDisconnected):
                    matches = []
                    for reconcile in range(4):
                        owned = api.call("GET", "/v2/pods")
                        owned = owned.get("pods", []) if isinstance(owned, dict) else owned
                        matches = [p for p in owned if p.get("name") == payload["name"]]
                        if matches:
                            break
                        time.sleep(3)
                    if len(matches) != 1:
                        raise RuntimeError("CREATE_RESULT_UNCONFIRMED; DO_NOT_REPLAY") from None
                    created = matches[0]
                    log("CREATE_RECONCILED " + created["id"])
                pod_id = created["id"]
                state["pod_id"] = pod_id
                state.pop("pending_create_name", None)
                write(PILOT / "pilot-state.json", state)
                price = float(created["cost"])
                assert price <= MAX_COMPUTE_USD_PER_HOUR, "LIVE_PRICE_EXCEEDS_APPROVED_RATE"
                log(f"HOST_SELECTED {count}x {gpu} price={price:.2f}")
                break
            except RuntimeError as exc:
                if "UNCONFIRMED" in str(exc):
                    raise
                state.pop("pending_create_name", None)
                write(PILOT / "pilot-state.json", state)
                log(f"HOST_UNAVAILABLE {count}x {gpu}: {str(exc)[:90]}")
        else:
            raise RuntimeError("NO_SUITABLE_HOST_AVAILABLE")
        state["pod_id"] = pod_id
        write(PILOT / "pilot-state.json", state)
        log("DEPLOYED " + pod_id)
    for attempt in range(120):
        pod = api.call("GET", "/v2/pods/" + pod_id)
        if pod["status"] == "RUNNING" and pod.get("ssh", {}).get("direct"):
            return pod
        time.sleep(3)
    raise RuntimeError("PROVISIONING_TIMEOUT")


def trust_host_key(pod, work):
    proxy = pod["ssh"]["proxy"]
    assert proxy["host"] == "ssh.runpod.io"
    args = ["ssh", "-tt", "-i", KEY, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", proxy["username"] + "@" + proxy["host"]]
    for retry in range(4):
        r = subprocess.run(args, input="printf '\\nK_BEGIN\\n'; cat /etc/ssh/ssh_host_ed25519_key.pub; printf '\\nK_END\\n'; exit\n", capture_output=True, text=True, timeout=40)
        match = re.search(r"ssh-ed25519 ([A-Za-z0-9+/=]{40,})", r.stdout)
        if r.returncode == 0 and match:
            break
        time.sleep(3)
    else:
        raise RuntimeError("TRUSTED_PROXY_HOST_KEY_READ_FAILED")
    key = match.group(1)
    assert b"ssh-ed25519" in base64.b64decode(key)
    d = pod["ssh"]["direct"]
    known = f"[{d['host']}]:{d['port']}"
    subprocess.run(["ssh-keygen", "-R", known], capture_output=True)
    with Path("/Users/cortex/.ssh/known_hosts").open("a") as f:
        f.write(f"{known} ssh-ed25519 {key}\n")
    write(work / "ssh-host-key-proof.json", {"pod_id": pod["id"], "endpoint": known, "public_key_sha256": hashlib.sha256(("ssh-ed25519 " + key).encode()).hexdigest(), "verification": "AUTHENTICATED_PREVIOUSLY_TRUSTED_RUNPOD_SSH_PROXY"})


def fold_contract(pod, index, session, work):
    c = json.loads((KIT / "docs/runpod/RUNPOD_CONSTRAINED_CONTRACT_TEMPLATE_20261117.json").read_text())
    c.pop("model_threads", None)
    note = AUTHORIZATION_NOTE
    c.update(
        provider_container_disk_gb=200,
        status="APPROVED",
        owner="Sharath N. S. — explicit attached owner authorization (4-fold pilot)",
        pod_type=pod.get("gpu", {}).get("id", "UNKNOWN"),
        pod_id=pod["id"],
        container_image="runpod/base:1.0.2-ubuntu2404",
        fold_index=index,
        fold=CANONICAL_FOLDS[index],
        authorization="OWNER_APPROVED_20261119_RESUME_PREDECLARED_4FOLD_PILOT",
        authorization_sha256=hashlib.sha256(note.encode()).hexdigest(),
        pilot_protocol="docs/research/PHASE7A_G0_A6_60M_RAW_4FOLD_PILOT_PROTOCOL_20261118.json @ 0d159d1",
        **session,
    )
    path = work / "session-approved.json"
    write(path, c)
    path.chmod(0o600)
    contract(path)
    pod_binding(pod, c)
    return c, path


def arm(c, path, work, index):
    state = work / "controller"
    state.mkdir(mode=0o700, exist_ok=True)
    label = f"com.crypto2.phase7-pilot-fold{index:03d}.resume-{RESUME_TAG}"
    plist = Path("/Users/cortex/Library/LaunchAgents") / (label + ".plist")
    assert not plist.exists(), "EXISTING_LAUNCHD_JOB_REFUSED"
    body = {
        "Label": label,
        "ProgramArguments": ["/usr/bin/caffeinate", "-dimsu", "/Users/cortex/Projects/crypto2.0/.venv/bin/python", "/Users/cortex/.crypto2-transfer/run_controller_ipv4_20261118.py", str(KIT / "scripts/closure/runpod_stop_controller_phase7.py"), "--contract", str(path), "--state", str(state), "--local-root", LOCAL_ROOT, "--arm"],
        "RunAtLoad": False,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 15,
        "StandardOutPath": str(state / "stdout.log"),
        "StandardErrorPath": str(state / "stderr.log"),
    }
    plist.write_bytes(plistlib.dumps(body))
    plist.chmod(0o600)
    domain = "gui/" + str(os.getuid())
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True, capture_output=True)
    subprocess.run(["launchctl", "kickstart", domain + "/" + label], check=True, capture_output=True)
    seen = set()
    for _ in range(120):
        beat = state / "heartbeat.json"
        if beat.exists():
            b = json.loads(beat.read_text())
            assert b["pod_id"] == c["pod_id"] and b["contract_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
            seen.add(b["utc"])
            if len(seen) >= 2:
                break
        if (state / "stop-receipt.json").exists():
            raise RuntimeError("CONTROLLER_STOPPED_DURING_ARM")
        time.sleep(1)
    else:
        raise RuntimeError("TWO_CONTROLLER_HEARTBEATS_NOT_OBSERVED")
    assert json.loads((state / "permission-probe.json").read_text())["status"] == "PASS"
    log(f"CONTROLLER_ARMED fold{index:03d} {label}")


def arm_setup(c, path, work, index):
    state = work / "setup-watchdog"
    state.mkdir(mode=0o700, exist_ok=True)
    label = f"com.crypto2.phase7-pilot-setup{index:03d}.{RESUME_TAG}"
    plist = Path("/Users/cortex/Library/LaunchAgents") / (label + ".plist")
    body = {"Label": label, "ProgramArguments": ["/usr/bin/caffeinate", "-dimsu", "/Users/cortex/Projects/crypto2.0/.venv/bin/python", "/Users/cortex/.crypto2-transfer/pilot_setup_watchdog_20261118.py", "--contract", str(path), "--state", str(state), "--handoff", str(work / "setup-handoff.json")], "RunAtLoad": False, "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 15, "StandardOutPath": str(state / "stdout.log"), "StandardErrorPath": str(state / "stderr.log")}
    assert not plist.exists()
    plist.write_bytes(plistlib.dumps(body));plist.chmod(0o600)
    domain = "gui/" + str(os.getuid())
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True, capture_output=True)
    subprocess.run(["launchctl", "kickstart", domain + "/" + label], check=True, capture_output=True)
    seen = set()
    for _ in range(180):
        h = state / "heartbeat.json"
        if h.exists():
            beat = json.loads(h.read_text());assert beat["status"] == "ARMED_SETUP_ONLY" and beat["pod_id"] == c["pod_id"]
            seen.add(beat["utc"])
            if len(seen) >= 2:
                log(f"SETUP_WATCHDOG_ARMED fold{index:03d}")
                return
        if (state / "stop-receipt.json").exists():raise RuntimeError("SETUP_WATCHDOG_STOPPED")
        time.sleep(1)
    raise RuntimeError("SETUP_WATCHDOG_NOT_READY")


def upload_inputs(ssh, index):
    """Stream the verified 11 GB transfer set onto this Pod's own /workspace (no network volume)."""
    definition = json.loads(TRANSFER_DEFINITION.read_text())
    staging = Path(definition["staging_root"])
    paths = [r["path"] for r in definition["records"]]
    assert len(paths) == 2777 and all((staging / p).is_file() for p in paths), "LOCAL_TRANSFER_SET_INCOMPLETE"
    listing = PILOT / f"upload-list-fold{index:03d}-{RESUME_TAG}.txt"
    listing.write_text("\n".join(paths) + "\n")
    started = time.monotonic()
    log(f"UPLOAD_STARTED fold{index:03d} files={len(paths)} bytes={sum(r['bytes'] for r in definition['records'])}")
    tar = subprocess.Popen(["tar", "--no-mac-metadata", "--no-xattrs", "-C", str(staging), "-cf", "-", "-T", str(listing)], stdout=subprocess.PIPE, env={**os.environ, "COPYFILE_DISABLE": "1"})
    receive = subprocess.run([*ssh, "mkdir -p /workspace/phase7a-transfer && tar -xf - -C /workspace/phase7a-transfer"], stdin=tar.stdout, capture_output=True, timeout=7200)
    tar.stdout.close()
    assert tar.wait() == 0 and receive.returncode == 0, "INPUT_UPLOAD_FAILED " + receive.stderr.decode()[-300:]
    sizes = "python3 -c " + shlex.quote("import json,sys,os; d=json.load(sys.stdin); bad=[r['path'] for r in d['records'] if not os.path.isfile('/workspace/phase7a-transfer/'+r['path']) or os.path.getsize('/workspace/phase7a-transfer/'+r['path'])!=r['bytes']]; print('UPLOAD_SIZES_OK' if not bad else 'UPLOAD_BAD '+str(len(bad)))")
    out = subprocess.run([*ssh, sizes], input=TRANSFER_DEFINITION.read_text(), capture_output=True, text=True, timeout=120).stdout.strip()
    assert out == "UPLOAD_SIZES_OK", out
    log(f"UPLOAD_VERIFIED fold{index:03d} {time.monotonic() - started:.0f}s")


def install_supplement(ssh, scp, d, command, index):
    for supplement in SUPPLEMENTS:
        install_one_supplement(ssh, scp, d, command, index, *supplement)


def install_one_supplement(ssh, scp, d, command, index, SUPPLEMENT_DIR, SUPPLEMENT_FILES, SUPPLEMENT_APPLY, package_root):
    """Stage one verified daily Silver supplement once on the volume, then add-only install it."""
    assert hashlib.sha256(SUPPLEMENT_APPLY[0].read_bytes()).hexdigest() == SUPPLEMENT_APPLY[1]
    records = [*SUPPLEMENT_FILES, (SUPPLEMENT_APPLY[0].name, SUPPLEMENT_APPLY[1])]
    for name, digest in SUPPLEMENT_FILES:
        assert hashlib.sha256((SUPPLEMENT_DIR / name).read_bytes()).hexdigest() == digest
    check = "python3 -c " + shlex.quote("from pathlib import Path; import hashlib; p=Path(" + repr(package_root) + "); records=" + repr(records) + "; print('SUPPLEMENT_READY' if all((p/n).is_file() and hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in records) else 'SUPPLEMENT_MISSING')")
    if subprocess.check_output([*ssh, check], text=True, timeout=40).strip() != "SUPPLEMENT_READY":
        incoming = package_root + "-incoming-" + RESUME_TAG
        subprocess.run([*ssh, "mkdir -p " + shlex.quote(incoming)], check=True, timeout=30)
        subprocess.run([*scp, str(SUPPLEMENT_DIR / SUPPLEMENT_FILES[0][0]), str(SUPPLEMENT_DIR / SUPPLEMENT_FILES[1][0]), str(SUPPLEMENT_APPLY[0]), "root@" + d["host"] + ":" + incoming + "/"], check=True, timeout=1800)
        publish = "from pathlib import Path; import hashlib,os; src=Path(" + repr(incoming) + "); dst=Path(" + repr(package_root) + "); dst.mkdir(parents=True,exist_ok=True); records=" + repr(records) + "\nfor n,h in records:\n p=src/n; q=dst/n; assert hashlib.sha256(p.read_bytes()).hexdigest()==h; assert not q.exists() or hashlib.sha256(q.read_bytes()).hexdigest()==h\n if not q.exists(): os.rename(p,q)\nprint('PERSISTENT_SUPPLEMENT_VERIFIED')"
        command("python3 - <<'PKG'\n" + publish + "\nPKG\n", "persistent-supplement-" + SUPPLEMENT_APPLY[0].stem + ".log")
    # 2026-11-21: a full re-verify of 21k files on the network volume takes ~6 min and SSH keeps dropping during it.
    # Reuse an earlier PASS install receipt for this exact archive; the loader still checks every file's SHA-256 at prepare.
    archive_sha = SUPPLEMENT_FILES[0][1]
    prior = "python3 -c " + shlex.quote("import json,glob,sys; h=sys.argv[1]; ok=[f for f in glob.glob('/workspace/phase7a-supplement-audit/install-*.json') if (lambda d: d.get('status')=='PASS' and d.get('archive_sha256')==h and d.get('conflicts')==[])(json.load(open(f)))]; print('PRIOR_PASS '+sorted(ok)[0] if ok else 'NO_PRIOR_PASS')") + " " + archive_sha
    found = subprocess.check_output([*ssh, prior], text=True, timeout=60).strip()
    if found.startswith("PRIOR_PASS "):
        log(f"SUPPLEMENT_VERIFIED fold{index:03d} reused {found.split(' ', 1)[1]} archive={archive_sha[:12]}")
        return
    out = command("set -euo pipefail\npython3 -I " + shlex.quote(package_root + "/" + SUPPLEMENT_APPLY[0].name) + " --package " + shlex.quote(package_root) + " --inputs /workspace/phase7a-transfer --audit /workspace/phase7a-supplement-audit --tag " + shlex.quote(f"fold{index:03d}-{RESUME_TAG}") + "\n", "supplement-install-" + SUPPLEMENT_APPLY[0].stem + ".log")
    assert "SUPPLEMENT_VERIFIED" in out, "SUPPLEMENT_NOT_VERIFIED"
    log(f"SUPPLEMENT_VERIFIED fold{index:03d} " + out.strip().splitlines()[0][:300])


def read_remote(ssh, remote_path, timeout):
    """Read a small evidence file; retry a dropped SSH transport (exit 255) so a finished stage is not lost."""
    for attempt in range(6):
        try:
            return subprocess.check_output([*ssh, "cat " + shlex.quote(remote_path)], text=True, timeout=timeout)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            if attempt == 5 or (isinstance(exc, subprocess.CalledProcessError) and exc.returncode != 255):
                raise
            log(f"SSH_READ_RETRY {remote_path} attempt={attempt + 1}")
            time.sleep(10)


def run_stages(pod, c, path, work, index):
    ssh = ssh_args(pod, KEY)
    ssh[1:1] = ["-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3"]
    d = pod["ssh"]["direct"]
    state = work / "pipeline"
    state.mkdir(exist_ok=True)

    def command(script, name):
        # 2026-11-21: SSH kept dropping during multi-minute stages, so each command now runs detached on the Pod
        # (setsid nohup) and the Mac only polls for its exit code; a dropped poll is retried, not fatal.
        script = script.replace("/crypto2-session", LOCAL_ROOT)
        job = LOCAL_ROOT + "/control/jobs/" + name
        q = shlex.quote
        launch = ("set -e; mkdir -p " + q(LOCAL_ROOT + "/control/jobs") + "; mkdir " + q(job) + "; cat > " + q(job + "/script.sh") + "; cd /; "
                  "setsid nohup bash -c " + q("bash " + q(job + "/script.sh") + " > " + q(job + "/out") + " 2>&1; echo $? > " + q(job + "/rc.tmp") + "; mv " + q(job + "/rc.tmp") + " " + q(job + "/rc"))
                  + " < /dev/null > /dev/null 2>&1 &")
        for attempt in range(6):
            started = subprocess.run([*ssh, launch], input=script, text=True, capture_output=True, timeout=60)
            if started.returncode == 0:
                break
            exists = subprocess.run([*ssh, "test -f " + q(job + "/script.sh")], capture_output=True, timeout=30)
            if exists.returncode == 0:
                break  # The launch reached the Pod before the transport dropped; never start it twice.
            if started.returncode != 255 or attempt == 5:
                (state / name).write_text(started.stdout + started.stderr)
                raise RuntimeError(f"REMOTE_COMMAND_FAILED_{started.returncode}_{name}")
            time.sleep(10)
        misses, deadline = 0, time.monotonic() + 4 * 3600
        while True:
            poll = subprocess.run([*ssh, "cat " + q(job + "/rc") + " 2>/dev/null || echo RUNNING"], text=True, capture_output=True, timeout=30)
            if poll.returncode == 0 and poll.stdout.strip() != "RUNNING":
                code = int(poll.stdout.strip())
                break
            misses = misses + 1 if poll.returncode else 0
            if misses >= 30 or time.monotonic() > deadline:
                raise RuntimeError(f"REMOTE_COMMAND_POLL_LOST_{name}")
            time.sleep(15)
        (state / name).write_text(read_remote(ssh, job + "/out", 120))
        if code:
            print((state / name).read_text()[-4000:], flush=True)
            raise RuntimeError(f"REMOTE_COMMAND_FAILED_{code}_{name}")
        return (state / name).read_text()

    common = "set -euo pipefail\nsource /etc/rp_environment\nexport CRYPTO2_SOURCE_ROOT=/crypto2-session/source\nexport CRYPTO2_LOCAL_ROOT=/crypto2-session\nexport CRYPTO2_SESSION_CONTRACT=/crypto2-session/session-approved.json\nexport KIT=/crypto2-operator-kit\n"
    scp = ["scp", "-O", "-l", "2400", "-i", KEY, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10", "-P", str(d["port"])]
    subprocess.run([*ssh, ("umask 077; mkdir -p /crypto2-session/control; cat > /crypto2-session/session-approved.json").replace("/crypto2-session", LOCAL_ROOT)], input=path.read_text(), text=True, check=True, timeout=30)
    package_root = "/workspace/phase7a-source-packages/0034184cdf9f-opsfix8"
    check = "python3 -c " + shlex.quote("from pathlib import Path; import hashlib,json; p=Path(" + repr(package_root) + "); records=" + repr([SOURCE, KIT_ARCHIVE]) + "; print('PACKAGES_READY' if all((p/n).is_file() and hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in records) else 'PACKAGES_MISSING')")
    present = subprocess.check_output([*ssh, check], text=True, timeout=40).strip()
    if present != "PACKAGES_READY":
        incoming = package_root + "-incoming-" + RESUME_TAG
        subprocess.run([*ssh, "mkdir -p " + shlex.quote(incoming)], check=True, timeout=30)
        subprocess.run([*scp, str(BASE / SOURCE[0]), str(BASE / KIT_ARCHIVE[0]), "root@" + d["host"] + ":" + incoming + "/"], check=True, timeout=1800)
        publish = "from pathlib import Path; import hashlib,os; src=Path(" + repr(incoming) + "); dst=Path(" + repr(package_root) + "); dst.mkdir(parents=True,exist_ok=True); records=" + repr([SOURCE,KIT_ARCHIVE]) + "\nfor n,h in records:\n p=src/n; q=dst/n; assert hashlib.sha256(p.read_bytes()).hexdigest()==h; assert not q.exists() or hashlib.sha256(q.read_bytes()).hexdigest()==h\n if not q.exists(): os.rename(p,q)\nprint('PERSISTENT_SOURCE_PACKAGES_VERIFIED')"
        command("python3 - <<'PKG'\n" + publish + "\nPKG\n", "persistent-packages.log")
    log(f"PERSISTENT_PACKAGES_READY fold{index:03d}")
    install_supplement(ssh, scp, d, command, index)
    subprocess.run([*ssh, "cp " + shlex.quote(package_root + "/" + SOURCE[0]) + " " + shlex.quote(package_root + "/" + KIT_ARCHIVE[0]) + " " + shlex.quote(LOCAL_ROOT + "/")], check=True, timeout=45)
    command(
        common
        + f"""python3 - <<'REMOTE'
from pathlib import Path
import tarfile,hashlib,shutil
base=Path('/crypto2-session')
for name,digest,dest in [('{SOURCE[0]}','{SOURCE[1]}',base/'source'),('{KIT_ARCHIVE[0]}','{KIT_ARCHIVE[1]}',Path('/'))]:
    assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest
    if dest==base/'source' and dest.exists(): shutil.rmtree(dest)
    if dest==Path('/') and Path('/crypto2-operator-kit').exists(): shutil.rmtree('/crypto2-operator-kit')
    with tarfile.open(base/name) as t:
        members=t.getmembers()
        for m in members: assert not Path(m.name).is_absolute() and '..' not in Path(m.name).parts and (m.isfile() or m.isdir())
        dest.mkdir(parents=True,exist_ok=True); t.extractall(dest,members=members,filter='data')
    print('ARCHIVE_VERIFIED_EXTRACTED',name,flush=True)
REMOTE
""",
        "extract.log",
    )
    log(f"PACKAGES_VERIFIED fold{index:03d}")
    arm(c, path, work, index)
    write(work / "setup-handoff.json", {"controller_state": str(work / "controller"), "pod_id": c["pod_id"]})
    for stage in STAGES:
        assert datetime.now(UTC) < datetime.fromisoformat(c["hard_stop_utc"]), "PILOT_DEADLINE"
        beat = json.loads((work / "controller/heartbeat.json").read_text())
        assert beat["wallet_status"]["action"] == "CONTINUE" and (datetime.now(UTC) - datetime.fromisoformat(beat["utc"])).total_seconds() < 90, "CONTROLLER_NOT_HEALTHY"
        started = time.monotonic()
        if stage == "operator-tests":
            result = command(common + "/crypto2-session/source/.venv/bin/python -m pytest -q /crypto2-operator-kit/scripts/closure/test_runpod_phase7_ops.py\n", "operator-tests.log")
            assert OPERATOR_TESTS in result, "OPERATOR_TESTS_NOT_62"
            log(f"STAGE_PASS fold{index:03d} operator-tests")
            continue
        approval = ""
        if stage in ("prepare", "reload", "memory-probe", "train"):
            kind = {"prepare": "PREPARE", "reload": "PREPARE", "memory-probe": "PROBE", "train": "TRAIN"}[stage]
            doc = json.loads((KIT / f"docs/runpod/OWNER_CONSTRAINED_{kind}_TEMPLATE_20261117.json").read_text())
            doc.update(status="APPROVED", owner="Sharath N. S. — 2026-11-21 approval: all 16 folds, budget-limited", stop_deadline_utc=c["hard_stop_utc"], cost_ceiling=c["max_session_usd"], authorization_reference="OWNER_APPROVED_20261121_ALL_16_FOLDS_8_40_USD_8H; ACTIVATED ONLY AFTER PRIOR STAGE PASS")
            doc["binding"]["fold_id"] = c["fold"]
            target = "/crypto2-session/owner-" + kind.lower() + "-approved.json"
            payload = json.dumps(doc, indent=2) + "\n"
            (state / Path(target).name).write_text(payload)
            command("umask 077\ncat > " + shlex.quote(target) + " <<'APPROVAL_JSON'\n" + payload + "APPROVAL_JSON\n", "approval-" + stage + ".log")
            approval = " --approval " + shlex.quote(target)
        log(f"STAGE_STARTED fold{index:03d} {stage}")
        python = "python3" if stage == "bootstrap" else "/crypto2-session/source/.venv/bin/python"
        command(common + python + " /crypto2-operator-kit/scripts/closure/runpod_phase7_ops.py " + stage + " --execute" + approval + "\n", stage + ".log")
        receipt = json.loads(read_remote(ssh, LOCAL_ROOT + "/evidence/" + stage + ".json", 30))
        assert receipt["status"] == "PASS" and receipt["pod_id"] == c["pod_id"]
        write(state / (stage + ".json"), receipt)
        log(f"STAGE_PASS fold{index:03d} {stage} {time.monotonic() - started:.0f}s")
    result = json.loads(read_remote(ssh, LOCAL_ROOT + "/evidence/train-result.json", 60))
    write(state / "train-result.json", result)
    report = result["reports"][0]
    assert report["fold_id"] == c["fold"], "TRAINED_FOLD_MISMATCH"
    log(f"MODEL fold{index:03d} {report['fold_id']} sha256={report['model_artifact_sha256']}")
    # 2026-11-21: models live on the Pod's container disk, which is wiped on stop; download before stopping.
    try:
        dest = MODEL_DOWNLOADS / f"fold{index:03d}-{report['fold_id']}"
        dest.mkdir(parents=True, exist_ok=True)
        with (state / "model-download.log").open("w") as err:
            # Benchmark mode writes <output_root>/.../model.joblib (not models/); locate it by its SHA-256 and take its folder.
            finder = "import hashlib,os,sys; r=sys.argv[1]; h=sys.argv[2]\nfor d,_,fs in os.walk(r):\n if '/cache' in d or '/source' in d: continue\n for f in fs:\n  p=os.path.join(d,f)\n  if os.path.getsize(p)<2**31 and hashlib.sha256(open(p,'rb').read()).hexdigest()==h: print(os.path.relpath(d,r)); sys.exit()\nsys.exit('MODEL_FILE_NOT_FOUND')"
            remote = "set -e; d=$(python3 -c " + shlex.quote(finder) + " " + shlex.quote(LOCAL_ROOT) + " " + report["model_artifact_sha256"] + "); tar -C " + shlex.quote(LOCAL_ROOT) + " -cf - \"$d\""
            tar = subprocess.Popen([*ssh, remote], stdout=subprocess.PIPE, stderr=err)
            untar = subprocess.run(["tar", "-xf", "-", "-C", str(dest)], stdin=tar.stdout, stderr=err, timeout=3600)
            tar.stdout.close()
            assert tar.wait(timeout=60) == 0 and untar.returncode == 0, "MODEL_DOWNLOAD_FAILED"
        files = [p for p in dest.rglob("*") if p.is_file()]
        digests = {str(p.relative_to(dest)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        write(dest / "SHA256SUMS.json", digests)
        found = report["model_artifact_sha256"] in digests.values()
        log(f"MODEL_DOWNLOADED fold{index:03d} files={len(files)} bytes={sum(p.stat().st_size for p in files)} artifact_sha_match={found} dest={dest}")
    except Exception as exc:  # never lose the run over a download; the fold report is already saved
        log(f"MODEL_DOWNLOAD_FAILED fold{index:03d} {type(exc).__name__}: {exc}")
    return report


def main():
    global LOCAL_ROOT
    PILOT.mkdir(mode=0o700, exist_ok=True)
    authorized = AUTHORIZATION_PATH.exists() and json.loads(AUTHORIZATION_PATH.read_text()).get("new_compute_or_training_authorized") is True
    if (PILOT / "OWNER_STOP_20261121b.json").exists() or (PILOT / "OWNER_STOP_20261121.json").exists() or (PILOT / "OWNER_STOP_20261120.json").exists() or (PILOT / "OWNER_STOP_20261119.json").exists() or ((PILOT / "OWNER_STOP_20261118.json").exists() and not authorized):
        log("OWNER_HOLD; no compute or training; explicit new authorization and fresh cost/deadline required")
        return 0
    state_path = PILOT / "pilot-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"completed": []}
    session = pilot_session()
    for index in FOLDS:
        if index in state["completed"]:
            continue
        work = PILOT / f"fold{index:03d}-resume-{RESUME_TAG}"
        LOCAL_ROOT = f"/crypto2-pilot-sessions/fold{index:03d}-{RESUME_TAG}"
        work.mkdir(mode=0o700, exist_ok=True)
        w0, t0 = wallet(), time.monotonic()
        template = json.loads((KIT / "docs/runpod/RUNPOD_CONSTRAINED_CONTRACT_TEMPLATE_20261117.json").read_text())
        verdict = decision({**template, **session}, wallet_usd=w0, billed_usd=0.0, now=datetime.now(UTC))
        if verdict["action"] != "CONTINUE":
            log("PILOT_STOP_BEFORE_COMPUTE " + str(verdict["reason"]))
            return 1
        log(f"FOLD_START fold{index:03d} {CANONICAL_FOLDS[index]} wallet={w0:.4f}")
        assert w0 - 1.0 > session["all_in_usd_per_hour_upper_bound"] * 1.0, "INSUFFICIENT_SAFE_BUDGET_FOR_ANOTHER_FOLD"
        pod = c = None
        success = False
        try:
            pod = acquire_pod(state)
            trust_host_key(pod, work)
            c, path = fold_contract(pod, index, session, work)
            # Warm up the authenticated direct SSH route before starting the fail-closed controller.
            ssh = ssh_args(pod, KEY)
            init = "set -e; source /etc/rp_environment; test \"$RUNPOD_POD_ID\" = " + shlex.quote(pod["id"]) + "; umask 077; mkdir -p " + shlex.quote(LOCAL_ROOT + "/control") + "; cat > " + shlex.quote(LOCAL_ROOT + "/session-approved.json")
            for warmup in range(12):
                ready = subprocess.run([*ssh, "bash -c " + shlex.quote(init)], input=path.read_text(), text=True, capture_output=True, timeout=30)
                if ready.returncode == 0:
                    break
                write(work / f"ssh-warmup-{warmup}.json", {"returncode": ready.returncode, "stderr": ready.stderr[-1000:]})
                time.sleep(3)
            else:
                raise RuntimeError("DIRECT_SSH_NOT_READY; CONTROLLER_NOT_ARMED")
            log(f"DIRECT_SSH_READY fold{index:03d} root={LOCAL_ROOT}")
            arm_setup(c, path, work, index)
            report = run_stages(pod, c, path, work, index)
            success = True
        except BaseException as exc:
            # 2026-11-21: the controller stops the Pod on SESSION_COMPLETE, which the kit writes only after collect()
            # mirrored evidence, models and benchmarks to /workspace/phase7a-evidence/<pod>/. If that happened, the
            # fold is trained and its model is on the volume even though the receipt read lost the race.
            events = work / "controller/events.jsonl"
            if c is not None and not isinstance(exc, KeyboardInterrupt) and events.exists() and '"reason": "NORMAL_COMPLETE"' in events.read_text():
                report = {"fold_id": c["fold"], "model_artifact_sha256": "ON_VOLUME:/workspace/phase7a-evidence/" + c["pod_id"]}
                success = True
                log(f"MODEL_ON_VOLUME fold{index:03d} {c['fold']} pod={c['pod_id']} after {type(exc).__name__}")
            else:
                log(f"FOLD_FAILED fold{index:03d} {type(exc).__name__}: {exc}")
                traceback.print_exc()
        finally:
            if state.get("pending_create_name"):
                owned = api.call("GET", "/v2/pods")
                owned = owned.get("pods", []) if isinstance(owned, dict) else owned
                for pending in owned:
                    if pending.get("name") == state["pending_create_name"]:
                        stop(api, {"pod_id": pending["id"]}, work / "ambiguous-create-stop", "PILOT_SETUP_FAILURE")
            if pod is None and state.get("pod_id"):
                pod = {"id": state["pod_id"]}  # Also stop an owned Pod if provisioning failed before return.
            if pod is not None:
                stop(api, c or {"pod_id": pod["id"]}, work, "PILOT_FOLD_COMPLETE" if success else "PILOT_FOLD_FAILURE")
                for _ in range(40):
                    if api.call("GET", "/v2/pods/" + pod["id"])["status"] == "EXITED":
                        break
                    time.sleep(3)
                log(f"POD_EXITED {pod['id']}")
        if not success:
            log("PILOT_ABORTED")
            return 1
        time.sleep(20)
        w1 = wallet()
        state["completed"].append(index)
        state.setdefault("folds", {})[str(index)] = {"fold_id": CANONICAL_FOLDS[index], "pod_id": pod["id"], "wall_seconds": round(time.monotonic() - t0), "wallet_before": w0, "wallet_after_lagging": w1, "model_sha256": report["model_artifact_sha256"]}
        write(state_path, state)
        log(f"FOLD_DONE fold{index:03d} wall={state['folds'][str(index)]['wall_seconds']}s wallet={w1:.4f}")
    log("PILOT_ALL_FOLDS_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
