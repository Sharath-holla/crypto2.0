from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from crypto_ai.config import BinanceSettings
from crypto_ai.data.binance import ArchiveCandleBounds
from crypto_ai.data.ingestion import DownloadRequest, HistoricalDownloader
from crypto_ai.data.quality.engine import QualityEngine
from crypto_ai.data.quality.models import ValidationStatus
from crypto_ai.phase7 import acquisition
from crypto_ai.phase7.config import Phase7Config
from crypto_ai.phase7.registry import build_symbol_registry
from tests.factories import make_candle

FIRST_OPEN = datetime(2022, 1, 26, tzinfo=UTC)
END_EXCLUSIVE = datetime(2022, 4, 12, tzinfo=UTC)
COARSE_START = datetime(2022, 1, 1, tzinfo=UTC)
COARSE_END = datetime(2022, 5, 1, tzinfo=UTC)


class _DailyArchiveRows:
    source_identity = "binance_public_archive"
    row_source = "binance_usdm_futures_archive"
    source_transport = "archive"

    def __init__(self, missing: set[date] | None = None) -> None:
        self.missing = missing or set()
        self.kline_calls = 0

    def fetch_exchange_info(self, symbol: str) -> dict[str, object]:
        return {"symbol": symbol, "status": "INACTIVE"}

    def fetch_klines(
        self,
        *,
        start: datetime,
        end: datetime,
        **_: object,
    ) -> list:
        self.kline_calls += 1
        if start < FIRST_OPEN or start >= END_EXCLUSIVE or start.date() in self.missing:
            return []
        index = (start - FIRST_OPEN).days
        candle = make_candle(
            index,
            start=FIRST_OPEN,
            interval_minutes=24 * 60,
            symbol="1000BTTCUSDT",
            source="binance_usdm_futures_archive",
        )
        return [candle] if start <= candle.open_time < end else []


def _codes(report, status: ValidationStatus) -> set[str]:
    return {check.check_name for check in report.checks if check.status is status}


def _downloader(tmp_path: Path, client: _DailyArchiveRows) -> HistoricalDownloader:
    settings = BinanceSettings(
        symbol="1000BTTCUSDT",
        interval="1d",
        output_root=tmp_path / "bronze",
    )
    return HistoricalDownloader(settings, client)


def test_corrected_request_coexists_with_failed_manifest_and_reuses_partitions(
    tmp_path: Path,
) -> None:
    client = _DailyArchiveRows()
    downloader = _downloader(tmp_path, client)

    failed_manifest = downloader.download(DownloadRequest(start=COARSE_START, end=COARSE_END))
    calls_after_failed_request = client.kline_calls
    corrected_manifest = downloader.download(DownloadRequest(start=FIRST_OPEN, end=END_EXCLUSIVE))

    failed_report = QualityEngine().validate_manifest(failed_manifest)
    corrected_report = QualityEngine().validate_manifest(corrected_manifest)
    assert failed_manifest != corrected_manifest
    assert failed_manifest.exists() and corrected_manifest.exists()
    assert "empty_partition" in _codes(failed_report, ValidationStatus.FAIL)
    assert corrected_report.overall_status is ValidationStatus.PASS
    assert client.kline_calls == calls_after_failed_request


def test_interior_missing_day_remains_a_hard_quality_failure(tmp_path: Path) -> None:
    missing = date(2022, 2, 10)
    client = _DailyArchiveRows({missing})
    manifest = _downloader(tmp_path, client).download(
        DownloadRequest(start=FIRST_OPEN, end=END_EXCLUSIVE)
    )

    report = QualityEngine().validate_manifest(manifest)
    failed_codes = _codes(report, ValidationStatus.FAIL)

    assert report.overall_status is ValidationStatus.FAIL
    assert "empty_partition" in failed_codes
    assert "manifest_timestamp_range" not in failed_codes


def test_acquire_candle_family_passes_verified_bounds_to_downloader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = build_symbol_registry(
        {"symbols": []},
        [
            {
                "symbol": "1000BTTCUSDT",
                "first_market_data_time": COARSE_START,
                "last_market_data_time": COARSE_END - timedelta(minutes=5),
                "available_until": COARSE_END,
                "available_intervals": ["5m", "12h", "1d"],
                "availability_evidence": "OFFICIAL_ARCHIVE_PERIOD_EVIDENCE",
            }
        ],
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        research_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    )
    exact = ArchiveCandleBounds(
        first_open_time=FIRST_OPEN,
        last_open_time=END_EXCLUSIVE - timedelta(days=1),
        end_exclusive=END_EXCLUSIVE,
        inspected_objects=("first.zip", "last.zip"),
    )
    requests: list[DownloadRequest] = []
    inspected_ranges: list[tuple[datetime, datetime]] = []

    class FakeArchiveClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def inspect_interval_bounds(self, **kwargs: object) -> ArchiveCandleBounds:
            inspected_ranges.append(
                (kwargs["archive_start"], kwargs["archive_end"])  # type: ignore[arg-type]
            )
            return exact

    class FakeDownloader:
        def __init__(self, *_: object) -> None:
            pass

        def download(self, request: DownloadRequest) -> Path:
            requests.append(request)
            return tmp_path / "bronze-manifest.json"

    monkeypatch.setattr(Phase7Config, "assert_cloud_execution_allowed", lambda _: None)
    monkeypatch.setattr(acquisition, "BinanceArchiveClient", FakeArchiveClient)
    monkeypatch.setattr(acquisition, "HistoricalDownloader", FakeDownloader)
    monkeypatch.setattr(
        acquisition,
        "_candle_settings",
        lambda *_args, **_kwargs: BinanceSettings(
            symbol="1000BTTCUSDT",
            interval="1d",
            output_root=tmp_path / "bronze",
        ),
    )
    monkeypatch.setattr(
        acquisition,
        "_promote_candles",
        lambda *_args, **_kwargs: tmp_path / "silver-manifest.json",
    )

    result = acquisition.acquire_candle_family(
        Phase7Config(),
        registry,
        symbols=("1000BTTCUSDT",),
        interval="1d",
        start=COARSE_START,
        end=COARSE_END,
    )

    assert inspected_ranges == [(COARSE_START, COARSE_END)]
    assert len(requests) == 1
    assert requests[0].start_utc == FIRST_OPEN
    assert requests[0].end_utc == END_EXCLUSIVE
    assert result == {"1000BTTCUSDT": str((tmp_path / "silver-manifest.json").resolve())}
