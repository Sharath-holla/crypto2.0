"""Read-only live catalog, wallet and stopped-Pod snapshot. Never deploys anything."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from runpod_phase7_ops import VOLUME, write
from runpod_stop_controller_phase7 import API


def candidates(gpus, cpu_catalogs):
    rows = []
    for g in gpus["gpus"]:
        dc = next((x for x in g.get("dataCenters", []) if x["id"] == "EU-SE-1"), None)
        if not dc or dc.get("availability") not in {"HIGH", "MEDIUM", "LOW"}:
            continue
        ram = float(g.get("minRam", 0)) * 1e9
        cpus = float(g.get("minVcpuCount", 0))
        rows.append(
            {
                "type": g["id"],
                "count": 1,
                "region": "EU-SE-1",
                "compute_usd_per_hour": g["price"]["secure"],
                "catalog_minimum_ram_bytes": ram,
                "catalog_minimum_vcpu": cpus,
                "candidate_meets_catalog_floor": ram >= 64 * 1024**3 and cpus >= 8,
                "status": "INSIDE_CONTAINER_RESOURCE_AND_LOCAL_DISK_PROBE_STILL_REQUIRED",
            }
        )
    for count, catalog in cpu_catalogs.items():
        for cpu in catalog["cpus"]:
            dc = next((x for x in cpu.get("dataCenters", []) if x["id"] == "EU-SE-1"), None)
            if not dc or dc.get("availability") not in {"HIGH", "MEDIUM", "LOW"}:
                continue
            ram = float(cpu["ramGbPerVcpu"]) * count * 1e9
            rows.append(
                {
                    "type": cpu["id"],
                    "vcpu_count": count,
                    "region": "EU-SE-1",
                    "compute_usd_per_hour": cpu["price"]["securePerVcpu"] * count,
                    "catalog_minimum_ram_bytes": ram,
                    "catalog_minimum_vcpu": count,
                    "candidate_meets_catalog_floor": ram >= 64 * 1024**3 and count >= 8,
                    "status": "INSIDE_CONTAINER_RESOURCE_AND_LOCAL_DISK_PROBE_STILL_REQUIRED",
                }
            )
    return sorted(rows, key=lambda x: x["compute_usd_per_hour"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-key-file", default="~/.crypto2-transfer/runpod-api-key")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    api = API(args.api_key_file)
    volume = api.call("GET", "/v2/network-volumes/" + VOLUME)
    if volume["dataCenter"] != "EU-SE-1" or volume["size"] != 50:
        raise ValueError("VOLUME_LAYOUT_CHANGED")
    old = api.call("GET", "/v2/pods/3hv6n675gud1wu")
    gpus = api.call(
        "GET",
        "/v2/catalog/gpus?include=AVAILABILITY&product=POD&count=1&cloud=SECURE&countryCodes=SE",
    )
    cpus = {
        n: api.call("GET", f"/v2/catalog/cpus?include=AVAILABILITY&product=POD&vcpuCount={n}")
        for n in (8, 16, 32)
    }
    wallet = api.call(
        "POST", "/graphql", {"query": "query { myself { clientBalance currentSpendPerHr } }"}
    )
    rows = candidates(gpus, cpus)
    admitted = [x for x in rows if x["candidate_meets_catalog_floor"]]
    write(
        args.output,
        {
            "captured_utc": datetime.now(UTC).isoformat(),
            "read_only": True,
            "volume": volume,
            "previous_pod": {
                k: old[k]
                for k in ("id", "status", "cost", "disk", "image", "dataCenterId", "createdAt")
            },
            "wallet": wallet["data"]["myself"],
            "candidates_price_order": rows,
            "cheapest_catalog_candidate": admitted[0] if admitted else None,
            "selection_status": "CANDIDATE_REQUIRES_ACTUAL_PROBE"
            if admitted
            else "NO_QUALIFIED_LIVE_CATALOG_CANDIDATE",
            "cost_scenarios": [
                {
                    "type": x["type"],
                    "compute_usd_per_hour": x["compute_usd_per_hour"],
                    "local_disk_gb_planning_example": 200,
                    "network_gb_existing": 50,
                    "all_in_estimated_usd_by_hours": {
                        str(h): h * (x["compute_usd_per_hour"] + 200 * 0.10 / 720 + 50 * 0.07 / 720)
                        for h in (1, 2, 4)
                    },
                }
                for x in rows
            ],
            "rates_note": (
                "Public storage reference; 720h planning month, taxes excluded; "
                "re-query deployment quote before approval. No runtime promise."
            ),
        },
    )
    print("READ_ONLY_CATALOG_SAVED " + args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
