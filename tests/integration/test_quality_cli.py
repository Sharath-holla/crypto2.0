from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from crypto_ai.cli import main
from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.storage import write_immutable
from tests.factories import make_candle
from tests.quality_helpers import write_bronze_dataset


def _last_json(output: str) -> dict:
    return json.loads(output.strip().splitlines()[-1])


def test_quality_report_cli_writes_json_and_human_summary(tmp_path: Path, capsys) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(minutes=10), [make_candle(0), make_candle(1)])],
    )

    exit_code = main(
        [
            "quality-report",
            "--manifest",
            str(manifest_path),
            "--output-root",
            str(tmp_path / "quality"),
        ]
    )
    output = capsys.readouterr().out
    payload = _last_json(output)

    assert exit_code == 0
    assert "DATA QUALITY REPORT" in output
    assert payload["overall_status"] == "PASS"
    assert Path(payload["report"]).exists()


def test_quality_report_cli_validates_existing_file_without_download(
    tmp_path: Path, capsys
) -> None:
    path = tmp_path / "existing.parquet"
    write_immutable(
        path,
        candles_to_table([make_candle(0), make_candle(1)]),
        metadata={"interval": "5m"},
    )

    exit_code = main(
        [
            "quality-report",
            "--path",
            str(path),
            "--symbol",
            "BTCUSDT",
            "--interval",
            "5m",
            "--output-root",
            str(tmp_path / "quality"),
        ]
    )
    payload = _last_json(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["overall_status"] == "PASS"


def test_promote_silver_cli_and_inspect_output(tmp_path: Path, capsys) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(minutes=10), [make_candle(0), make_candle(1)])],
    )

    exit_code = main(
        [
            "promote-silver",
            "--manifest",
            str(manifest_path),
            "--quality-root",
            str(tmp_path / "quality"),
            "--silver-root",
            str(tmp_path / "silver"),
            "--quarantine-root",
            str(tmp_path / "quarantine"),
        ]
    )
    promotion = _last_json(capsys.readouterr().out)
    silver_path = Path(promotion["output_files"][0])

    assert exit_code == 0
    assert promotion["promoted"] is True
    assert main(["inspect", str(silver_path), "--limit", "1"]) == 0
    inspect_output = capsys.readouterr().out
    assert '"row_count": 2' in inspect_output
    assert '"layer": "silver"' in inspect_output


def test_failed_quality_gate_cli_creates_quarantine_without_silver(tmp_path: Path, capsys) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    invalid = replace(make_candle(), high=Decimal("1"))
    manifest_path, _ = write_bronze_dataset(
        tmp_path,
        [(start, start + timedelta(minutes=5), [invalid])],
    )

    exit_code = main(
        [
            "promote-silver",
            "--manifest",
            str(manifest_path),
            "--quality-root",
            str(tmp_path / "quality"),
            "--silver-root",
            str(tmp_path / "silver"),
            "--quarantine-root",
            str(tmp_path / "quarantine"),
        ]
    )
    payload = _last_json(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["promoted"] is False
    assert Path(payload["quarantine_record"]).exists()
    assert not list((tmp_path / "silver").rglob("*.parquet"))
