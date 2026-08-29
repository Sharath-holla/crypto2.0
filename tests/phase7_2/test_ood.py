from __future__ import annotations

from crypto_ai.phase7_2.ood import ListingAgeStatus, OODReason, RobustOODModel
from crypto_ai.phase7_2.schemas import DataQualityStatus


def _model() -> RobustOODModel:
    return RobustOODModel.fit(
        (
            {"momentum": -2.0, "volatility": 1.0},
            {"momentum": -1.0, "volatility": 2.0},
            {"momentum": 0.0, "volatility": 3.0},
            {"momentum": 1.0, "volatility": 4.0},
            {"momentum": 2.0, "volatility": 5.0},
        ),
        train_symbols=("BTCUSDT", "ETHUSDT"),
        extreme_threshold=4.0,
    )


def test_in_distribution_assessment_is_monitor_only() -> None:
    result = _model().assess(
        {"momentum": 0.0, "volatility": 3.0},
        symbol="BTCUSDT",
        listing_age_days=365,
        data_quality_status=DataQualityStatus.VALID,
    )
    assert result.is_ood is False
    assert result.ood_score == 0
    assert result.reason_codes == ()
    assert result.row_rejected is False


def test_extreme_feature_is_detected() -> None:
    result = _model().assess(
        {"momentum": 100.0, "volatility": 3.0},
        symbol="BTCUSDT",
        listing_age_days=365,
        data_quality_status=DataQualityStatus.VALID,
    )
    assert OODReason.FEATURE_EXTREME in result.reason_codes
    assert result.feature_extremeness > 4


def test_unseen_symbol_and_young_listing_are_distinct() -> None:
    result = _model().assess(
        {"momentum": 0.0, "volatility": 3.0},
        symbol="NEWUSDT",
        listing_age_days=5,
        data_quality_status=DataQualityStatus.VALID,
    )
    assert result.unseen_symbol is True
    assert result.listing_age_status is ListingAgeStatus.YOUNG
    assert result.reason_codes == (OODReason.UNSEEN_SYMBOL, OODReason.YOUNG_LISTING)


def test_stale_data_is_not_treated_as_neutral() -> None:
    result = _model().assess(
        {"momentum": 0.0, "volatility": 3.0},
        symbol="BTCUSDT",
        listing_age_days=365,
        data_quality_status=DataQualityStatus.STALE,
    )
    assert result.reason_codes == (OODReason.STALE_DATA,)


def test_missing_feature_is_explicit() -> None:
    result = _model().assess(
        {"momentum": None, "volatility": 3.0},
        symbol="BTCUSDT",
        listing_age_days=365,
        data_quality_status=DataQualityStatus.MISSING,
    )
    assert result.reason_codes == (OODReason.MISSING_FEATURE, OODReason.INVALID_DATA)


def test_score_and_reason_codes_are_deterministic() -> None:
    kwargs = {
        "symbol": "NEWUSDT",
        "listing_age_days": 2,
        "data_quality_status": DataQualityStatus.STALE,
        "model_disagreement": 0.5,
    }
    first = _model().assess({"momentum": 100.0, "volatility": None}, **kwargs)
    second = _model().assess({"volatility": None, "momentum": 100.0}, **kwargs)
    assert first == second
