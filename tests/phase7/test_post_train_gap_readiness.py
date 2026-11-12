"""Post-TRAIN gap readiness is a report only and never restores membership look-ahead."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from crypto_ai.phase7.readiness import post_train_gap_readiness


def _t(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


@dataclass(frozen=True)
class Plan:
    fold_id: str = "fold-001-test"
    train_end: datetime = _t(2022, 1, 1)
    validation_start: datetime = _t(2022, 1, 1)
    validation_end: datetime = _t(2022, 4, 1)
    calibration_start: datetime = _t(2022, 4, 1)
    calibration_end: datetime = _t(2022, 7, 1)
    test_start: datetime = _t(2022, 7, 1)
    test_end: datetime = _t(2022, 10, 1)


@dataclass(frozen=True)
class Gap:
    symbol: str
    start: datetime
    end: datetime
    interval: str = "5m"
    partition: str = "p"


def test_no_gaps_means_ready() -> None:
    report = post_train_gap_readiness([Plan()], [])
    assert report["all_folds_ready"] and report["blocked_fold_count"] == 0
    assert report["folds"][0]["status"] == "READY"
    assert report["train_membership_effect"] == "NONE_REPORT_ONLY"


def test_gaps_are_assigned_to_the_segments_they_make_unusable() -> None:
    gaps = [
        Gap("AAAUSDT", _t(2022, 2, 1), _t(2022, 2, 2)),  # validation
        Gap("BBBUSDT", _t(2022, 4, 20), _t(2022, 4, 21)),  # cal A (before 2022-05-16 midpoint)
        Gap("CCCUSDT", _t(2022, 6, 20), _t(2022, 6, 21)),  # cal B
        Gap("DDDUSDT", _t(2022, 8, 1), _t(2022, 8, 2)),  # test
    ]
    fold = post_train_gap_readiness([Plan()], gaps)["folds"][0]
    assert fold["status"] == "BLOCKED_POST_TRAIN_GAP"
    assert fold["blocked_segment_names"] == ["CAL_A", "CAL_B", "TEST", "VALIDATION"]
    by_symbol = {item["symbol"]: item["segment"] for item in fold["blocked_segments"]}
    assert by_symbol == {
        "AAAUSDT": "VALIDATION",
        "BBBUSDT": "CAL_A",
        "CCCUSDT": "CAL_B",
        "DDDUSDT": "TEST",
    }


def test_gap_spanning_two_segments_blocks_both() -> None:
    gap = Gap("AAAUSDT", _t(2022, 3, 31), _t(2022, 4, 2))
    names = post_train_gap_readiness([Plan()], [gap])["folds"][0]["blocked_segment_names"]
    assert names == ["CAL_A", "VALIDATION"]


def test_train_history_gaps_and_other_folds_are_not_post_train_blocks() -> None:
    history = Gap("AAAUSDT", _t(2021, 6, 1), _t(2021, 6, 2))
    touching = Gap("AAAUSDT", _t(2021, 12, 31), _t(2022, 1, 1))  # ends exactly at TRAIN end
    later = Gap("AAAUSDT", _t(2022, 10, 1), _t(2022, 10, 2))  # starts at test_end
    assert post_train_gap_readiness([Plan()], [history, touching, later])["all_folds_ready"]


def test_active_symbol_filter_and_conservative_default() -> None:
    gap = Gap("ZZZUSDT", _t(2022, 8, 1), _t(2022, 8, 2))
    conservative = post_train_gap_readiness([Plan()], [gap])
    assert conservative["membership_filter"] == "NOT_APPLIED_CONSERVATIVE"
    assert conservative["blocked_fold_count"] == 1
    filtered = post_train_gap_readiness(
        [Plan()], [gap], active_symbols_by_fold={"fold-001-test": ["AAAUSDT"]}
    )
    assert filtered["all_folds_ready"] and filtered["membership_filter"] == "FOLD_ACTIVE_SYMBOLS"
    active = post_train_gap_readiness(
        [Plan()], [gap], active_symbols_by_fold={"fold-001-test": ["zzzusdt"]}
    )
    assert active["blocked_fold_count"] == 1


def test_report_is_deterministic_and_input_order_independent() -> None:
    gaps = [
        Gap("BBBUSDT", _t(2022, 8, 1), _t(2022, 8, 2)),
        Gap("AAAUSDT", _t(2022, 2, 1), _t(2022, 2, 2)),
    ]
    assert post_train_gap_readiness([Plan()], gaps) == post_train_gap_readiness(
        [Plan()], list(reversed(gaps))
    )
