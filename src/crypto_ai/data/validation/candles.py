from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pyarrow as pa

from crypto_ai.data.quality.checks import validate_partition
from crypto_ai.data.quality.models import ValidationContext, ValidationStatus
from crypto_ai.data.quality.policy import QualityPolicy


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    message: str
    examples: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QualityReport:
    row_count: int
    interval: str
    errors: list[QualityIssue] = field(default_factory=list)
    warnings: list[QualityIssue] = field(default_factory=list)
    duplicate_count: int = 0
    gap_count: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "row_count": self.row_count,
            "interval": self.interval,
            "duplicate_count": self.duplicate_count,
            "gap_count": self.gap_count,
            "errors": [asdict(issue) for issue in self.errors],
            "warnings": [asdict(issue) for issue in self.warnings],
        }


def _examples(indexes: list[int], limit: int = 10) -> list[str]:
    return [str(index) for index in indexes[:limit]]


def validate_candles(table: pa.Table, interval: str) -> QualityReport:
    rich = validate_partition(
        table,
        ValidationContext(symbol=None, interval=interval),
        QualityPolicy(),
    )
    report = QualityReport(
        row_count=table.num_rows,
        interval=interval,
        duplicate_count=int(rich.metrics.get("duplicate_count", 0)),
        gap_count=int(rich.metrics.get("number_of_missing_candles", 0)),
    )
    advanced_only = {
        "taker_buy_base_exceeds_volume",
        "taker_buy_quote_exceeds_volume",
        "positive_volume_without_trades",
        "stale_flat_run",
        "candidate_price_outlier",
    }
    for result in rich.checks:
        if result.check_name in advanced_only:
            continue
        issue = QualityIssue(result.check_name, result.message, result.examples)
        if result.check_name == "zero_volume":
            report.warnings.append(issue)
        elif result.status is ValidationStatus.FAIL:
            report.errors.append(issue)
            if result.check_name in {
                "negative_base_volume",
                "negative_quote_volume",
                "negative_taker_buy_base_volume",
                "negative_taker_buy_quote_volume",
            } and not any(existing.code == "negative_volume" for existing in report.errors):
                report.errors.append(
                    QualityIssue("negative_volume", result.message, result.examples)
                )
        elif result.status is ValidationStatus.WARN:
            report.warnings.append(issue)
    if report.duplicate_count and not any(
        issue.code == "non_monotonic_timestamp" for issue in report.errors
    ):
        report.errors.append(
            QualityIssue(
                "non_monotonic_timestamp",
                "open_time is not strictly increasing",
            )
        )
    return report
