"""Authenticated read-only real-mode smoke check; credentials remain in memory."""

from __future__ import annotations

import json

import httpx

from .config import CONFIG_HASH, CryptoPaths, require_branch
from .dev import private_environment


def main():
    paths = CryptoPaths.from_environment()
    require_branch(paths.repo)
    private = private_environment(paths)
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
        assert client.get("http://127.0.0.1:3010").status_code == 200
        assert client.get("http://127.0.0.1:8010/health/ready").status_code == 200
        assert client.get("http://127.0.0.1:8011/health").status_code == 401
        login = client.post(
            "http://127.0.0.1:8010/auth/login",
            json={
                "email": private["OWNER_EMAIL"],
                "password": private["OWNER_PASSWORD"],
            },
        )
        login.raise_for_status()
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        response = client.get("http://127.0.0.1:8010/crypto/project", headers=headers)
        response.raise_for_status()
        snapshot = response.json()["snapshot"]
        identity = snapshot["identity"]
        assert identity["mode"] == "REAL_CRYPTO_STATE"
        assert identity["configuration_hash"] == CONFIG_HASH
        assert identity["folds_expected"] == 16 and identity["specs_expected"] == 48
        assert identity["prospective_holdout_status"] == "LOCKED_UNUSED"
        assert identity["prospective_holdout_used"] is False
        assert identity["prospective_holdout_evaluation_authorized"] is False
        assert identity["july_2026_used"] is False
        jobs = client.get("http://127.0.0.1:8010/crypto/jobs", headers=headers)
        jobs.raise_for_status()
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": identity["mode"],
                "frontend": "http://127.0.0.1:3010",
                "backend": "http://127.0.0.1:8010",
                "private_adapter_auth": "PASS",
                "configuration_hash": CONFIG_HASH,
                "canonical_models": len(snapshot["models"]),
                "canonical_folds": len(snapshot["folds"]),
                "gold": snapshot["dataset"]["status"],
                "lineage": snapshot["lineage"]["full_lineage_closure"],
                "observed_jobs": len(jobs.json()),
                "scientific_job_started_by_probe": False,
                "holdout": "LOCKED_UNUSED",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
