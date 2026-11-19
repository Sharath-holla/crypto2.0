"""Outside-Pod control-plane stop controller. No start/create/delete/resize operation.

Default only validates/plans. --arm requires the fresh owner session contract.
Run under a supervised, awake Mac process; never copy the account API key to a Pod.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

from runpod_phase7_ops import POD_LOCAL, VOLUME, contract, read, sha, write
from runpod_wallet_policy_phase7 import decision


class API:
    def __init__(self, key_file):
        path = Path(key_file).expanduser()
        if path.stat().st_mode & 0o077:
            raise ValueError("API_KEY_FILE_MUST_BE_PRIVATE")
        self.key = path.read_text().strip()

    def call(self, method, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(
            "https://api.runpod.io" + path,
            data=body,
            method=method,
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
        )
        read_only = method == "GET" or (
            method == "POST"
            and path == "/graphql"
            and isinstance(data, dict)
            and str(data.get("query", "")).lstrip().startswith("query")
        )
        # Two short read attempts take less than the former single 20-second
        # timeout. Mutations are never automatically replayed here.
        attempts = 2 if read_only else 1
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=6 if read_only else 20) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if read_only and attempt == 0 and exc.code in {429, 502, 503, 504}:
                    time.sleep(0.5)
                    continue
                # Never dump response body, request headers or credentials.
                raise RuntimeError(f"RUNPOD_API_HTTP_{exc.code}") from None
            except (TimeoutError, urllib.error.URLError):
                if read_only and attempt == 0:
                    time.sleep(0.5)
                    continue
                raise RuntimeError("RUNPOD_API_NETWORK_UNAVAILABLE") from None


def stop_contract(args):
    """An expired, previously armed contract still authorizes stopping its exact Pod."""
    state = Path(args.state).expanduser()
    if (state / "permission-probe.json").is_file():
        proof = read(state / "permission-probe.json")
        c = read(args.contract)
        if (proof.get("status"), proof.get("pod_id"), proof.get("contract_sha256")) == (
            "PASS",
            c.get("pod_id"),
            sha(args.contract),
        ):
            return c
    try:
        return contract(args.contract)
    except ValueError as exc:
        if str(exc) != "SESSION_EXPIRED":
            raise
        state = Path(args.state).expanduser()
        proof = read(state / "permission-probe.json")
        c = read(args.contract)
        if (proof.get("status"), proof.get("pod_id"), proof.get("contract_sha256")) != (
            "PASS",
            c.get("pod_id"),
            sha(args.contract),
        ):
            raise ValueError("EXPIRED_CONTRACT_HAS_NO_PRIOR_ARM_PROOF") from None
        return c


def pod_binding(pod, c):
    if c["volume_id"] == POD_LOCAL:
        if pod["id"] != c["pod_id"] or pod["dataCenterId"] != c["region"]:
            raise ValueError("POD_BINDING_CHANGED")
        if (pod.get("mounts") or {}).get("network"):
            raise ValueError("NETWORK_VOLUME_BINDING_CHANGED")
    else:
        if pod["id"] != c["pod_id"] or pod["dataCenterId"] != "EU-SE-1":
            raise ValueError("POD_BINDING_CHANGED")
        if {"path": "/workspace", "volumeId": VOLUME} not in pod["mounts"]["network"]:
            raise ValueError("NETWORK_VOLUME_BINDING_CHANGED")
    if pod["locked"] or pod["disk"] < c["provider_container_disk_gb"]:
        raise ValueError("POD_LOCKED_OR_DISK_QUOTA_CHANGED")
    if float(pod["cost"]) > float(c["compute_usd_per_hour"]):
        raise ValueError("LIVE_PRICE_EXCEEDS_OWNER_APPROVAL")
    if pod["image"] != c["container_image"]:
        raise ValueError("CONTAINER_IMAGE_DIFFERS_FROM_OWNER_APPROVAL")
    allocation = pod.get("gpu") or pod.get("cpu") or {}
    floor_gib = 45 if c.get("resource_profile") == "constrained_48gb" else 64
    if float(allocation.get("memory", 0)) * 1e9 < floor_gib * 1024**3:
        raise ValueError("PROVIDER_RAM_ALLOCATION_BELOW_PROFILE_FLOOR")


def ssh_args(pod, key):
    direct = pod["ssh"]["direct"]
    if not direct:
        raise ValueError("DIRECT_SSH_NOT_READY")
    host = direct["host"]
    ipaddress.ip_address(host)
    port = int(direct["port"])
    if not 1 <= port <= 65535:
        raise ValueError("INVALID_SSH_PORT")
    return [
        "ssh",
        "-i",
        str(Path(key).expanduser()),
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "root@" + host,
    ]


def download_pod_evidence(ssh, pod_id, state):
    """Pod-local placement: copy this Pod's exported evidence (model included) to the Mac.

    The container disk is lost when the Pod stops, so this runs before the stop. Fail soft:
    three attempts, then record the failure and stop anyway (spending limits come first).
    """
    target = state / "pod-evidence"
    for attempt in range(3):
        archive = state / f"pod-evidence-{attempt}.tar"
        with archive.open("wb") as out:
            result = subprocess.run(
                [*ssh, "tar -C /workspace/phase7a-evidence -cf - " + shlex.quote(pod_id)],
                stdout=out,
                stderr=subprocess.PIPE,
                timeout=900,
            )
        if result.returncode == 0:
            target.mkdir(exist_ok=True)
            subprocess.run(["tar", "-xf", str(archive), "-C", str(target)], check=True)
            archive.unlink()
            write(state / "pod-evidence-download.json", {"status": "PASS", "path": str(target)})
            return True
    write(state / "pod-evidence-download.json", {"status": "FAIL_STOPPED_ANYWAY"})
    return False


def remote(ssh, script, payload=None, timeout=25):
    result = subprocess.run(
        [*ssh, script],
        input=None if payload is None else json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError("SSH_CONTROL_CHANNEL_FAILED")
    return result.stdout


def transition(state, name, **fields):
    record = {"state": name, "utc": datetime.now(UTC).isoformat(), **fields}
    write(state / "run-state.json", record)
    with (state / "events.jsonl").open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        import os

        os.fsync(stream.fileno())


def verify_remote_checkpoint(ssh, local, receipt, request_id=None, timeout=20):
    path = Path(receipt["checkpoint_path"])
    if not path.is_relative_to(Path("/workspace/phase7a-evidence/training-checkpoints")):
        raise ValueError("PERSISTENT_CHECKPOINT_PATH_REFUSED")
    command = [
        str(local / "source/.venv/bin/python"),
        "-m",
        "crypto_ai.phase7.preemption",
        "verify",
        "--checkpoint",
        str(path),
        "--expect-identities",
        "/crypto2-operator-kit/docs/runpod/identity.expected.json",
    ]
    if request_id:
        command += ["--request-id", request_id]
    value = json.loads(
        remote(
            ssh,
            "cd "
            + shlex.quote(str(local / "source"))
            + "; "
            + "env PYTHONPATH="
            + shlex.quote(str(local / "source/src") + ":" + str(local / "source"))
            + " "
            + " ".join(shlex.quote(s) for s in command),
            timeout=timeout,
        )
    )
    if value["checkpoint_sha256"] != receipt["checkpoint_sha256"]:
        raise ValueError("PERSISTENT_CHECKPOINT_RECEIPT_HASH_MISMATCH")
    if value.get("native_parse_verified") is not True:
        raise ValueError("PERSISTENT_NATIVE_CHECKPOINT_NOT_VERIFIED")
    return value


def graceful_checkpoint(ssh, local, state, seconds, reason):
    """Bounded small native checkpoint/metadata transfer only. Never copy a cache here."""
    request_id = uuid.uuid4().hex
    deadline = time.monotonic() + seconds
    transition(state, "CHECKPOINT_REQUESTED", reason=reason, request_id=request_id)
    path = local / "control/CHECKPOINT_REQUEST.json"
    script = (
        "import sys,json,os; from pathlib import Path; p=Path(sys.argv[1]); "
        "p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix('.tmp'); "
        "s=t.open('w'); json.dump(json.load(sys.stdin),s); s.flush(); os.fsync(s.fileno()); "
        "s.close(); os.replace(t,p)"
    )
    remote(
        ssh,
        "python3 -c " + shlex.quote(script) + " " + shlex.quote(str(path)),
        {"request_id": request_id, "reason": reason},
        timeout=min(20, seconds),
    )
    receipt_path = local / "control/checkpoint-receipt.json"
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        raw = remote(
            ssh,
            "if test -f "
            + shlex.quote(str(receipt_path))
            + "; then cat "
            + shlex.quote(str(receipt_path))
            + "; fi",
            timeout=min(5, remaining),
        )
        if raw:
            receipt = json.loads(raw)
            if (
                receipt.get("request_id") == request_id
                and receipt.get("state") == "EVIDENCE_EXPORTED"
            ):
                transition(state, "CHECKPOINT_WRITTEN", request_id=request_id)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                verified = verify_remote_checkpoint(
                    ssh, local, receipt, request_id, timeout=min(20, remaining)
                )
                transition(state, "CHECKPOINT_VERIFIED", checkpoint=verified)
                write(state / "last-verified-checkpoint.json", verified)
                transition(state, "EVIDENCE_EXPORTED", checkpoint=verified)
                return verified
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    transition(state, "CHECKPOINT_TIMEOUT", fallback="LAST_ALREADY_PERSISTED_CHECKPOINT_OR_RESTART")
    return None


def stop(api, c, state, reason):
    # Even expiry must permit stopping, so do not revalidate the now-expired contract here.
    write(state / "stop-request.json", {"reason": reason, "utc": datetime.now(UTC).isoformat()})
    for attempt in range(30):
        try:
            pod = api.call("GET", "/v2/pods/" + c["pod_id"])
            if pod["status"] == "EXITED":
                if c.get("volume_id") == POD_LOCAL:
                    preserved = "NONE_POD_CONTAINER_DISK"
                else:
                    volume = api.call("GET", "/v2/network-volumes/" + VOLUME)
                    if volume["id"] != VOLUME:
                        raise ValueError("VOLUME_NOT_CONFIRMED")
                    preserved = VOLUME
                write(
                    state / "stop-receipt.json",
                    {
                        "status": "STOPPED_CONFIRMED",
                        "reason": reason,
                        "pod_id": c["pod_id"],
                        "provider_status": "EXITED",
                        "volume_preserved": preserved,
                        "utc": datetime.now(UTC).isoformat(),
                    },
                )
                transition(
                    state,
                    "PROVIDER_EXITED",
                    reason=reason,
                    pod_id=c["pod_id"],
                    volume_preserved=preserved,
                )
                return
            api.call("POST", "/v2/pods/" + c["pod_id"] + "/action", {"action": "stop"})
        except Exception:
            pass
        time.sleep(min(2 + attempt, 10))
    raise RuntimeError("CRITICAL_STOP_NOT_CONFIRMED; use RunPod console immediately")


def pause_message(state, wallet):
    if not (state / "last-verified-checkpoint.json").is_file():
        print("TRAINING STOPPED — no verified partial checkpoint; restart after new approval.")
        return
    saved = read(state / "last-verified-checkpoint.json")
    print("TRAINING PAUSED SAFELY", flush=True)
    print("Completed rounds: " + str(saved["completed_rounds"]) + " / 500")
    print("Best iteration: " + str(saved["best_iteration"]))
    print("Best validation RMSE: " + str(saved["best_validation_rmse"]))
    print("Saved checkpoint: " + saved["checkpoint_path"])
    print("Saved on persistent storage: YES")
    print("Prepared cache retained: " + ("YES" if saved.get("cache_retained") else "NO"))
    print("Last observed wallet: $" + str(wallet) + " (provider billing may lag)")
    print("Pod: EXITED")
    print("MID_FIT_RESUME_NOT_QUALIFIED: restart at round 0 on the same qualified cache.")
    print(
        "After top-up: obtain fresh RESUME ONE CPU SMOKE approval, then run "
        "runpod_resume_one_smoke_phase7.sh --execute --approval <fresh-approval> "
        "--checkpoint " + saved["checkpoint_path"]
    )


def monitor(args):
    c = contract(args.contract)
    if sys.platform != "darwin":
        raise ValueError("OUTSIDE_POD_MAC_CONTROLLER_REQUIRED")
    api = API(args.api_key_file)
    state = Path(args.state).expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True)
    pod = api.call("GET", "/v2/pods/" + c["pod_id"])
    if pod["status"] == "EXITED":
        stop(api, c, state, "ALREADY_STOPPED")
        return
    if c.get("previous_pod_id"):
        old = api.call("GET", "/v2/pods/" + c["previous_pod_id"])
        if old["status"] != "EXITED":
            raise ValueError("PREVIOUS_POD_MUST_BE_CONFIRMED_EXITED")
    pod_binding(pod, c)
    if pod["status"] != "RUNNING" or "stop" not in pod["actions"]:
        raise ValueError("RUNNING_STOPPABLE_POD_REQUIRED")
    # Non-disruptive permission probe: locked is already false. This is a no-op,
    # uses the same documented pods:write scope as the stop transition.
    api.call("PATCH", "/v2/pods/" + c["pod_id"], {"locked": False})
    pod = api.call("GET", "/v2/pods/" + c["pod_id"])
    pod_binding(pod, c)
    if "stop" not in pod["actions"]:
        raise ValueError("STOP_TRANSITION_UNAVAILABLE")
    write(
        state / "permission-probe.json",
        {
            "status": "PASS",
            "method": "same-scope no-op pods:write PATCH + unlocked stop action",
            "pod_id": c["pod_id"],
            "actual_stop_tested": False,
            "contract_sha256": sha(args.contract),
        },
    )
    ssh = ssh_args(pod, args.ssh_key)
    local = Path(args.local_root)
    if not local.is_absolute() or local == Path("/") or local.is_relative_to(Path("/workspace")):
        raise ValueError("LOCAL_CONTROL_PATH_REQUIRED")
    heartbeat = local / "control/stop-controller.json"
    stop_request = local / "control/STOP_REQUEST.json"
    complete_request = local / "control/SESSION_COMPLETE.json"
    # Wallet/control-plane status is operational evidence, separate from model metrics.
    last_wallet = c["wallet_usd_at_start"]
    last_billed = 0.0
    verdict = None
    reason = "OWNER_STOP"
    transition(state, "RUNNING", pod_id=c["pod_id"])
    try:
        while True:
            now = datetime.now(UTC)
            try:
                pod = api.call("GET", "/v2/pods/" + c["pod_id"])
                if pod["status"] == "EXITED":
                    reason = "ALREADY_STOPPED"
                    break
                pod_binding(pod, c)
                wallet = api.call(
                    "POST",
                    "/graphql",
                    {"query": "query { myself { clientBalance currentSpendPerHr } }"},
                )["data"]["myself"]
                last_wallet = float(wallet["clientBalance"])
                costs = []
                billed = [("pods", "podId", c["pod_id"])]
                if c["volume_id"] != POD_LOCAL:
                    billed.append(("network-volumes", "networkVolumeId", VOLUME))
                for family, field, resource in billed:
                    query = urllib.parse.urlencode(
                        {
                            "startTime": c["session_start_utc"],
                            "endTime": now.isoformat(),
                            "bucketSize": "hour",
                            field: resource,
                        }
                    )
                    bill = api.call("GET", "/v2/billing/" + family + "?" + query)
                    costs.append(float(bill["metadata"]["totals"]["totalAmount"]))
                last_billed = sum(costs)
                conservative_contract = {
                    **c,
                    "all_in_usd_per_hour_upper_bound": max(
                        c["all_in_usd_per_hour_upper_bound"], float(wallet["currentSpendPerHr"])
                    ),
                }
                verdict = decision(
                    conservative_contract, wallet_usd=last_wallet, billed_usd=last_billed, now=now
                )
                if verdict["action"] == "EMERGENCY_STOP":
                    reason = verdict["reason"]
                    break
                # Distinct explicit stop reasons; a completed model is already exported.
                signal_text = remote(
                    ssh,
                    "if test -e "
                    + shlex.quote(str(complete_request))
                    + "; then printf NORMAL_COMPLETE; elif test -e "
                    + shlex.quote(str(stop_request))
                    + "; then printf INVARIANT_FAILURE; elif test -e "
                    + shlex.quote(str(local / "control/OWNER_STOP.json"))
                    + "; then printf OWNER_STOP; elif test -e "
                    + shlex.quote(str(local / "control/SESSION_PAUSED.json"))
                    + "; then printf MODEL_ALREADY_PREEMPTED; elif test -e "
                    + shlex.quote("/tmp/crypto2-phase7-stop-" + c["pod_id"] + ".json")
                    + "; then printf RESOURCE_FAILURE; fi",
                )
                if signal_text:
                    reason = signal_text
                    if reason == "NORMAL_COMPLETE":
                        if c["volume_id"] == POD_LOCAL:
                            download_pod_evidence(ssh, c["pod_id"], state)
                        break
                    if reason == "MODEL_ALREADY_PREEMPTED":
                        raw = remote(
                            ssh,
                            "cat " + shlex.quote(str(local / "control/checkpoint-receipt.json")),
                        )
                        verified = verify_remote_checkpoint(ssh, local, json.loads(raw))
                        write(state / "last-verified-checkpoint.json", verified)
                        reason = "OWNER_STOP"
                        verdict = None
                        break
                    verdict = decision(
                        conservative_contract,
                        wallet_usd=last_wallet,
                        billed_usd=last_billed,
                        now=now,
                        reason=reason,
                    )
                    if reason in {"RESOURCE_FAILURE", "INVARIANT_FAILURE"}:
                        verdict["grace_seconds"] = 0
                        verdict["action"] = "EMERGENCY_STOP"
                if verdict["action"] != "CONTINUE":
                    reason = verdict["reason"]
                    break
                receipt = {
                    "status": "ARMED",
                    "utc": now.isoformat(),
                    "pod_id": c["pod_id"],
                    "contract_sha256": sha(args.contract),
                    "stop_permission_verified": True,
                    "permission_method": "same pods:write scope; unlocked; stop available",
                    "wallet_status": verdict,
                    "wallet": wallet,
                    "provider_billed_usd_lagging": last_billed,
                    "provider_allocation": {
                        k: pod.get(k)
                        for k in (
                            "gpu",
                            "cpu",
                            "disk",
                            "image",
                            "dataCenterId",
                            "createdAt",
                            "startedAt",
                        )
                    },
                    "process": "outside-Pod Mac; launchd + caffeinate required",
                }
                # Fetch the small latest receipt; independently validate a new checkpoint once.
                raw = remote(
                    ssh,
                    "if test -f "
                    + shlex.quote(str(local / "control/checkpoint-receipt.json"))
                    + "; then cat "
                    + shlex.quote(str(local / "control/checkpoint-receipt.json"))
                    + "; fi",
                )
                if raw:
                    latest = json.loads(raw)
                    old = (
                        read(state / "last-verified-checkpoint.json")
                        if (state / "last-verified-checkpoint.json").exists()
                        else {}
                    )
                    if latest.get("checkpoint_sha256") != old.get("checkpoint_sha256"):
                        verified = verify_remote_checkpoint(ssh, local, latest)
                        write(state / "last-verified-checkpoint.json", verified)
                    receipt["latest_persisted_checkpoint"] = read(
                        state / "last-verified-checkpoint.json"
                    )
                write(state / "heartbeat.json", receipt)
                print(
                    json.dumps(
                        {
                            "operational_wallet_status": verdict,
                            "latest_checkpoint": receipt.get("latest_persisted_checkpoint"),
                        }
                    ),
                    flush=True,
                )
                # Write then rename: a stage must never read a truncated, empty heartbeat.
                remote(
                    ssh,
                    "mkdir -p "
                    + shlex.quote(str(heartbeat.parent))
                    + "; cat > "
                    + shlex.quote(str(heartbeat) + ".tmp")
                    + " && mv -f "
                    + shlex.quote(str(heartbeat) + ".tmp")
                    + " "
                    + shlex.quote(str(heartbeat)),
                    receipt,
                )
            except Exception as exc:
                verdict = decision(
                    c, wallet_usd=last_wallet, billed_usd=last_billed, api_healthy=False
                )
                reason = "API_HEALTH_FAILURE"
                write(state / "api-health-failure.json", {"error_type": type(exc).__name__})
                break
            time.sleep(20)
    except BaseException:
        reason = "OWNER_STOP"
        verdict = decision(c, wallet_usd=last_wallet, billed_usd=last_billed, reason=reason)
        raise
    finally:
        if verdict and verdict["grace_seconds"] >= 5:
            verdict = decision(
                locals().get("conservative_contract", c),
                wallet_usd=last_wallet,
                billed_usd=last_billed,
                reason=reason,
            )
        if verdict and verdict["grace_seconds"] >= 5:
            try:
                graceful_checkpoint(ssh, local, state, verdict["grace_seconds"], reason)
            except Exception as exc:
                transition(
                    state,
                    "CHECKPOINT_UNAVAILABLE",
                    error_type=type(exc).__name__,
                    fallback="LAST_ALREADY_PERSISTED_VERIFIED_CHECKPOINT_OR_ROUND_ZERO",
                )
        # Never copy GB of cache or a whole source/output tree at the wallet safety boundary.
        transition(
            state,
            "PROVIDER_STOP_REQUESTED",
            reason=reason,
            wallet_status=verdict,
            uses_last_persisted_checkpoint=True,
        )
        stop(api, c, state, reason)
        if reason != "NORMAL_COMPLETE":
            pause_message(state, last_wallet)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contract", required=True)
    p.add_argument("--arm", action="store_true")
    p.add_argument("--api-key-file", default="~/.crypto2-transfer/runpod-api-key")
    p.add_argument("--ssh-key", default="~/.ssh/runpod_crypto2")
    p.add_argument("--local-root", default="/crypto2-session")
    p.add_argument("--state", default="~/.crypto2-transfer/phase7-20261118-controller")
    args = p.parse_args()
    if not args.arm:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_ONLY",
                    "armed": False,
                    "required": (
                        "fresh owner contract; outside-Pod process; "
                        "same-scope write permission probe; live rate; SSH trust"
                    ),
                }
            )
        )
        return 0
    try:
        monitor(args)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        # Initialization failures must not strand an authorized running Pod.
        try:
            c = stop_contract(args)
            stop(
                API(args.api_key_file),
                c,
                Path(args.state).expanduser(),
                "CONTROLLER_INITIALIZATION_FAILURE",
            )
            print("CONTROLLER_FAILED_COMPUTE_STOP_CONFIRMED")
            return 0  # No billable compute remains; do not restart a failed controller forever.
        except Exception:
            print(
                "CRITICAL: compute stop unconfirmed. Use the RunPod console before leaving.",
                file=sys.stderr,
            )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
