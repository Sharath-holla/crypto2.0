from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from crypto_ai.phase7_2.schemas import DataQualityStatus

OOD_ASSESSMENT_VERSION = "ood_assessment_v1"


class OODReason(StrEnum):
    MISSING_FEATURE = "MISSING_FEATURE"
    STALE_DATA = "STALE_DATA"
    INVALID_DATA = "INVALID_DATA"
    UNSEEN_SYMBOL = "UNSEEN_SYMBOL"
    YOUNG_LISTING = "YOUNG_LISTING"
    FEATURE_EXTREME = "FEATURE_EXTREME"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"


class ListingAgeStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    YOUNG = "YOUNG"
    ESTABLISHED = "ESTABLISHED"


@dataclass(frozen=True, slots=True)
class OODAssessment:
    is_ood: bool
    ood_score: float
    reason_codes: tuple[OODReason, ...]
    feature_extremeness: float
    unseen_symbol: bool
    listing_age_status: ListingAgeStatus
    data_quality_status: DataQualityStatus
    model_disagreement: float | None
    row_rejected: bool = False
    schema_version: str = OOD_ASSESSMENT_VERSION

    def __post_init__(self) -> None:
        if not 0 <= self.ood_score <= 1 or not math.isfinite(self.ood_score):
            raise ValueError("ood_score must be finite and between zero and one")
        if self.feature_extremeness < 0 or not math.isfinite(self.feature_extremeness):
            raise ValueError("feature_extremeness must be finite and nonnegative")
        if self.model_disagreement is not None and (
            self.model_disagreement < 0 or not math.isfinite(self.model_disagreement)
        ):
            raise ValueError("model_disagreement must be finite and nonnegative")
        if tuple(dict.fromkeys(self.reason_codes)) != self.reason_codes:
            raise ValueError("OOD reason codes must be unique and deterministic")
        if self.row_rejected:
            raise ValueError("Phase 7.2 OOD assessment is monitor-only by default")


@dataclass(frozen=True, slots=True)
class RobustOODModel:
    feature_names: tuple[str, ...]
    medians: tuple[float, ...]
    robust_scales: tuple[float, ...]
    train_symbols: frozenset[str]
    extreme_threshold: float = 6.0
    young_listing_days: int = 30
    disagreement_threshold: float = 0.25

    def __post_init__(self) -> None:
        if not self.feature_names or self.feature_names != tuple(sorted(self.feature_names)):
            raise ValueError("feature_names must be non-empty and sorted")
        if not (len(self.feature_names) == len(self.medians) == len(self.robust_scales)):
            raise ValueError("OOD distribution vectors must have matching lengths")
        if any(scale <= 0 or not math.isfinite(scale) for scale in self.robust_scales):
            raise ValueError("robust scales must be finite and positive")
        if self.extreme_threshold <= 0 or self.young_listing_days < 0:
            raise ValueError("OOD thresholds must be valid")
        if self.disagreement_threshold <= 0:
            raise ValueError("disagreement_threshold must be positive")

    @classmethod
    def fit(
        cls,
        rows: Iterable[Mapping[str, float]],
        *,
        train_symbols: Iterable[str],
        extreme_threshold: float = 6.0,
        young_listing_days: int = 30,
        disagreement_threshold: float = 0.25,
    ) -> RobustOODModel:
        supplied = tuple(rows)
        if not supplied:
            raise ValueError("TRAIN rows are required to fit OOD baseline")
        feature_names = tuple(sorted(supplied[0]))
        if not feature_names or any(tuple(sorted(row)) != feature_names for row in supplied):
            raise ValueError("all TRAIN OOD rows must share one feature schema")
        matrix = np.asarray(
            [[float(row[name]) for name in feature_names] for row in supplied],
            dtype=np.float64,
        )
        if not np.all(np.isfinite(matrix)):
            raise ValueError("TRAIN OOD features must be finite")
        medians = np.median(matrix, axis=0)
        lower = np.percentile(matrix, 25, axis=0)
        upper = np.percentile(matrix, 75, axis=0)
        scales = (upper - lower) / 1.349
        scales = np.where(scales > 1e-12, scales, 1.0)
        symbols = frozenset(symbol.strip().upper() for symbol in train_symbols)
        if not symbols or any(not symbol for symbol in symbols):
            raise ValueError("TRAIN symbols are required")
        return cls(
            feature_names=feature_names,
            medians=tuple(float(value) for value in medians),
            robust_scales=tuple(float(value) for value in scales),
            train_symbols=symbols,
            extreme_threshold=extreme_threshold,
            young_listing_days=young_listing_days,
            disagreement_threshold=disagreement_threshold,
        )

    def assess(
        self,
        features: Mapping[str, float | None],
        *,
        symbol: str,
        listing_age_days: int | None,
        data_quality_status: DataQualityStatus,
        model_disagreement: float | None = None,
    ) -> OODAssessment:
        reasons: list[OODReason] = []
        missing = [name for name in self.feature_names if features.get(name) is None]
        if missing:
            reasons.append(OODReason.MISSING_FEATURE)

        if data_quality_status is DataQualityStatus.STALE:
            reasons.append(OODReason.STALE_DATA)
        elif data_quality_status is not DataQualityStatus.VALID:
            reasons.append(OODReason.INVALID_DATA)

        normalized_symbol = symbol.strip().upper()
        unseen_symbol = normalized_symbol not in self.train_symbols
        if unseen_symbol:
            reasons.append(OODReason.UNSEEN_SYMBOL)

        if listing_age_days is None:
            listing_status = ListingAgeStatus.UNKNOWN
        elif listing_age_days < 0:
            raise ValueError("listing_age_days cannot be negative")
        elif listing_age_days < self.young_listing_days:
            listing_status = ListingAgeStatus.YOUNG
            reasons.append(OODReason.YOUNG_LISTING)
        else:
            listing_status = ListingAgeStatus.ESTABLISHED

        extremeness = 0.0
        for index, name in enumerate(self.feature_names):
            value = features.get(name)
            if value is None:
                continue
            numeric = float(value)
            if not math.isfinite(numeric):
                if OODReason.MISSING_FEATURE not in reasons:
                    reasons.append(OODReason.MISSING_FEATURE)
                continue
            score = abs(numeric - self.medians[index]) / self.robust_scales[index]
            extremeness = max(extremeness, score)
        if extremeness > self.extreme_threshold:
            reasons.append(OODReason.FEATURE_EXTREME)

        if model_disagreement is not None:
            if model_disagreement < 0 or not math.isfinite(model_disagreement):
                raise ValueError("model_disagreement must be finite and nonnegative")
            if model_disagreement > self.disagreement_threshold:
                reasons.append(OODReason.MODEL_DISAGREEMENT)

        categorical_flag = 1.0 if reasons else 0.0
        scaled_extreme = min(1.0, extremeness / self.extreme_threshold)
        scaled_disagreement = (
            min(1.0, model_disagreement / self.disagreement_threshold)
            if model_disagreement is not None and self.disagreement_threshold > 0
            else 0.0
        )
        order = {reason: index for index, reason in enumerate(OODReason)}
        reason_codes = tuple(sorted(set(reasons), key=order.__getitem__))
        return OODAssessment(
            is_ood=bool(reason_codes),
            ood_score=max(categorical_flag, scaled_extreme, scaled_disagreement),
            reason_codes=reason_codes,
            feature_extremeness=extremeness,
            unseen_symbol=unseen_symbol,
            listing_age_status=listing_status,
            data_quality_status=data_quality_status,
            model_disagreement=model_disagreement,
        )
