from __future__ import annotations

import json
from pathlib import Path

from crypto_ai.data.ingestion.manifest import write_manifest
from crypto_ai.phase4_1.reconcile import reconcile_archive_with_rest


def test_reconciliation_replaces_only_proven_discrepant_partition(tmp_path: Path) -> None:
    root = tmp_path / "bronze"
    manifests = root / "manifests"
    archive_path = manifests / "archive.json"
    rest_path = manifests / "rest.json"
    report_path = tmp_path / "equivalence.json"
    archive_records = [
        {
            "partition_key": "1-2",
            "status": "complete",
            "file": "archive-1.parquet",
            "sha256": "archive-1",
            "row_count": 1,
        },
        {
            "partition_key": "2-3",
            "status": "complete",
            "file": "archive-2.parquet",
            "sha256": "archive-2",
            "row_count": 1,
        },
    ]
    write_manifest(
        archive_path,
        {
            "run_id": "archive-run",
            "source": "binance_public_archive",
            "partitions": archive_records,
            "file_locations": [item["file"] for item in archive_records],
            "row_count": 2,
        },
    )
    write_manifest(
        rest_path,
        {
            "run_id": "rest-run",
            "source": "binance",
            "partitions": [
                {
                    "partition_key": "2-3",
                    "status": "complete",
                    "file": "rest-2.parquet",
                    "sha256": "rest-2",
                    "row_count": 1,
                }
            ],
        },
    )
    write_manifest(report_path, {"equivalent": False})

    reconciled_path = reconcile_archive_with_rest(
        archive_path, (rest_path,), equivalence_reports=(report_path,)
    )
    reconciled = json.loads(reconciled_path.read_text(encoding="utf-8"))

    assert reconciled["partitions"][0]["file"] == "archive-1.parquet"
    assert reconciled["partitions"][0]["row_source"] == ("binance_usdm_futures_archive")
    assert reconciled["partitions"][1]["file"] == "rest-2.parquet"
    assert reconciled["partitions"][1]["row_source"] == "binance_usdm_futures_rest"
    assert reconciled["reconciliation"]["replaced_partition_count"] == 1
    assert reconciled["reconciliation"]["raw_sources_mutated"] is False
