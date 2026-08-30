from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

import pyarrow as pa

from crypto_ai.data.quality.models import (
    GapClassification,
    PartitionValidation,
    ValidationContext,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
)
from crypto_ai.data.quality.policy import QualityPolicy
from crypto_ai.data.schema import schema_errors
from crypto_ai.domain import interval_milliseconds


def _epoch_milliseconds(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    delta = normalized - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def _result(
    context: ValidationContext,
    check_name: str,
    status: ValidationStatus,
    severity: ValidationSeverity,
    message: str,
    *,
    observed_value: Any = None,
    expected_value: Any = None,
    affected_rows: int = 0,
    sample_rows: list[Any] | tuple[Any, ...] = (),
) -> ValidationResult:
    return ValidationResult(
        check_name=check_name,
        status=status,
        severity=severity,
        symbol=context.symbol,
        interval=context.interval,
        partition=context.partition,
        message=message,
        observed_value=observed_value,
        expected_value=expected_value,
        affected_rows=affected_rows,
        sample_rows=tuple(sample_rows),
    )


def _pass(context: ValidationContext, check_name: str, message: str) -> ValidationResult:
    return _result(
        context,
        check_name,
        ValidationStatus.PASS,
        ValidationSeverity.INFO,
        message,
    )


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _runs(indexes: list[int]) -> list[tuple[int, int]]:
    if not indexes:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = indexes[0]
    for index in indexes[1:]:
        if index != previous + 1:
            runs.append((start, previous))
            start = index
        previous = index
    runs.append((start, previous))
    return runs


def _gap_metrics(
    open_times: list[datetime],
    context: ValidationContext,
    interval_delta: timedelta,
    sample_limit: int,
) -> dict[str, Any]:
    unique_times = sorted(set(open_times))
    if context.range_start is not None and context.range_end is not None:
        expected_start = context.range_start.astimezone(UTC)
        expected_end = context.range_end.astimezone(UTC)
    elif unique_times:
        expected_start = unique_times[0]
        expected_end = unique_times[-1] + interval_delta
    else:
        expected_start = context.range_start
        expected_end = context.range_end

    if expected_start is None or expected_end is None or expected_start >= expected_end:
        expected_count = len(unique_times)
    else:
        expected_count = int((expected_end - expected_start) / interval_delta)

    missing_count = 0
    largest_gap = 0
    missing_samples: list[datetime] = []

    def add_gap(first_missing: datetime, count: int) -> None:
        nonlocal missing_count, largest_gap
        if count <= 0:
            return
        missing_count += count
        largest_gap = max(largest_gap, count)
        available = sample_limit - len(missing_samples)
        for offset in range(min(count, available)):
            missing_samples.append(first_missing + offset * interval_delta)

    if expected_start is not None and expected_end is not None:
        if not unique_times:
            add_gap(expected_start, expected_count)
        else:
            leading = int((unique_times[0] - expected_start) / interval_delta)
            add_gap(expected_start, max(0, leading))
            for previous, current in zip(unique_times, unique_times[1:], strict=False):
                difference = current - previous
                if difference > interval_delta and difference % interval_delta == timedelta(0):
                    add_gap(previous + interval_delta, int(difference / interval_delta) - 1)
            trailing = int((expected_end - (unique_times[-1] + interval_delta)) / interval_delta)
            add_gap(unique_times[-1] + interval_delta, max(0, trailing))

    percentage = (missing_count / expected_count * 100.0) if expected_count else 0.0
    return {
        "number_of_expected_candles": expected_count,
        "number_of_observed_candles": len(unique_times),
        "number_of_missing_candles": missing_count,
        "gap_percentage": percentage,
        "first_missing_timestamp": missing_samples[0] if missing_samples else None,
        "largest_gap": largest_gap,
        "sample_missing_timestamps": missing_samples,
        "gap_classification": GapClassification.UNKNOWN_GAP,
    }


def _detect_outliers(
    closes: list[Decimal],
    open_times: list[datetime],
    policy: QualityPolicy,
) -> list[dict[str, Any]]:
    if len(closes) < policy.outlier_min_observations + 2:
        return []
    with localcontext() as context:
        context.prec = 28
        returns = [
            closes[index] / closes[index - 1] - Decimal(1) for index in range(1, len(closes))
        ]
    threshold = Decimal(str(policy.outlier_mad_threshold))
    candidates: list[dict[str, Any]] = []
    for index, value in enumerate(returns):
        history_start = max(0, index - policy.outlier_window)
        history = returns[history_start:index]
        if len(history) < policy.outlier_min_observations:
            continue
        median = _median(history)
        mad = _median([abs(item - median) for item in history])
        deviation = abs(value - median)
        if mad == 0:
            is_candidate = deviation > 0
            score: Decimal | None = None
        else:
            score = deviation / mad
            is_candidate = score > threshold
        if is_candidate:
            candidates.append(
                {
                    "row": index + 1,
                    "open_time": open_times[index + 1],
                    "fractional_return": value,
                    "rolling_median": median,
                    "mad": mad,
                    "mad_score": score,
                }
            )
    return candidates


def validate_partition(
    table: pa.Table,
    context: ValidationContext,
    policy: QualityPolicy | None = None,
) -> PartitionValidation:
    policy = policy or QualityPolicy()
    validation = PartitionValidation(row_count=table.num_rows, interval=context.interval)
    checks = validation.checks
    metrics = validation.metrics

    drift = schema_errors(table.schema)
    if drift:
        for message in drift:
            checks.append(
                _result(
                    context,
                    "schema_mismatch",
                    ValidationStatus.FAIL,
                    ValidationSeverity.CRITICAL,
                    message,
                    observed_value=str(table.schema),
                    expected_value="canonical candle schema 1.0.0",
                )
            )
        metrics["schema_errors"] = len(drift)
        return validation

    null_counts = {name: table[name].null_count for name in table.column_names}
    null_counts = {name: count for name, count in null_counts.items() if count}
    if null_counts:
        for name, count in null_counts.items():
            checks.append(
                _result(
                    context,
                    "missing_required_value",
                    ValidationStatus.FAIL,
                    ValidationSeverity.CRITICAL,
                    f"{name} contains {count} null required values",
                    observed_value=count,
                    expected_value=0,
                    affected_rows=count,
                )
            )
        metrics["schema_errors"] = sum(null_counts.values())
        return validation
    checks.append(_pass(context, "schema", "Canonical columns, types, and nullability pass"))
    metrics["schema_errors"] = 0

    rows = table.to_pylist()
    open_times: list[datetime] = [row["open_time"] for row in rows]
    close_times: list[datetime] = [row["close_time"] for row in rows]
    interval_ms = interval_milliseconds(context.interval)
    interval_delta = timedelta(milliseconds=interval_ms)

    duplicate_indexes: list[int] = []
    exact_duplicate_indexes: list[int] = []
    conflicting_duplicate_indexes: list[int] = []
    seen: dict[tuple[str, datetime], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        identity = (row["symbol"], row["open_time"])
        previous = seen.get(identity)
        if previous is None:
            seen[identity] = row
            continue
        duplicate_indexes.append(index)
        if row == previous:
            exact_duplicate_indexes.append(index)
        else:
            conflicting_duplicate_indexes.append(index)
    metrics["duplicate_count"] = len(duplicate_indexes)
    metrics["exact_duplicates"] = len(exact_duplicate_indexes)
    metrics["conflicting_duplicates"] = len(conflicting_duplicate_indexes)
    if duplicate_indexes:
        allowed = (
            not conflicting_duplicate_indexes
            and len(exact_duplicate_indexes) <= policy.allowed_duplicate_count
        )
        checks.append(
            _result(
                context,
                "duplicate_timestamp",
                ValidationStatus.WARN if allowed else ValidationStatus.FAIL,
                ValidationSeverity.WARNING if allowed else ValidationSeverity.ERROR,
                f"Found {len(duplicate_indexes)} duplicate candle identities",
                observed_value=len(duplicate_indexes),
                expected_value=f"<= {policy.allowed_duplicate_count} exact, 0 conflicting",
                affected_rows=len(duplicate_indexes),
                sample_rows=duplicate_indexes[: policy.sample_limit],
            )
        )
    if exact_duplicate_indexes:
        checks.append(
            _result(
                context,
                "exact_duplicate",
                (
                    ValidationStatus.WARN
                    if len(exact_duplicate_indexes) <= policy.allowed_duplicate_count
                    else ValidationStatus.FAIL
                ),
                (
                    ValidationSeverity.WARNING
                    if len(exact_duplicate_indexes) <= policy.allowed_duplicate_count
                    else ValidationSeverity.ERROR
                ),
                "Field-identical duplicate candles were found",
                observed_value=len(exact_duplicate_indexes),
                expected_value=f"<= {policy.allowed_duplicate_count}",
                affected_rows=len(exact_duplicate_indexes),
                sample_rows=exact_duplicate_indexes[: policy.sample_limit],
            )
        )
    if conflicting_duplicate_indexes:
        checks.append(
            _result(
                context,
                "conflicting_duplicate",
                ValidationStatus.FAIL,
                ValidationSeverity.CRITICAL,
                "Duplicate candle identities contain conflicting field values",
                observed_value=len(conflicting_duplicate_indexes),
                expected_value=0,
                affected_rows=len(conflicting_duplicate_indexes),
                sample_rows=conflicting_duplicate_indexes[: policy.sample_limit],
            )
        )

    non_monotonic = [
        index for index in range(1, len(open_times)) if open_times[index] < open_times[index - 1]
    ]
    if non_monotonic:
        checks.append(
            _result(
                context,
                "non_monotonic_timestamp",
                ValidationStatus.FAIL,
                ValidationSeverity.ERROR,
                "open_time is not strictly increasing",
                affected_rows=len(non_monotonic),
                sample_rows=non_monotonic[: policy.sample_limit],
            )
        )

    misaligned = [
        index
        for index, timestamp in enumerate(open_times)
        if _epoch_milliseconds(timestamp) % interval_ms != 0
    ]
    if misaligned:
        checks.append(
            _result(
                context,
                "misaligned_open_time",
                ValidationStatus.FAIL,
                ValidationSeverity.ERROR,
                "open_time is not aligned to the configured UTC interval",
                observed_value=len(misaligned),
                expected_value=0,
                affected_rows=len(misaligned),
                sample_rows=misaligned[: policy.sample_limit],
            )
        )

    invalid_duration: list[int] = []
    invalid_order: list[int] = []
    for index, (open_time, close_time) in enumerate(zip(open_times, close_times, strict=True)):
        if open_time >= close_time:
            invalid_order.append(index)
        boundary = open_time + interval_delta
        if not boundary - timedelta(milliseconds=1) <= close_time < boundary:
            invalid_duration.append(index)
    if invalid_order:
        checks.append(
            _result(
                context,
                "open_not_before_close",
                ValidationStatus.FAIL,
                ValidationSeverity.CRITICAL,
                "open_time must be earlier than close_time",
                affected_rows=len(invalid_order),
                sample_rows=invalid_order[: policy.sample_limit],
            )
        )
    if invalid_duration:
        checks.append(
            _result(
                context,
                "invalid_close_time",
                ValidationStatus.FAIL,
                ValidationSeverity.ERROR,
                "close_time does not end immediately before the next interval boundary",
                affected_rows=len(invalid_duration),
                sample_rows=invalid_duration[: policy.sample_limit],
            )
        )

    sorted_unique_times = sorted(set(open_times))
    unexpected_interval = [
        index
        for index, (previous, current) in enumerate(
            zip(sorted_unique_times, sorted_unique_times[1:], strict=False), start=1
        )
        if (current - previous) % interval_delta != timedelta(0)
    ]
    if unexpected_interval:
        checks.append(
            _result(
                context,
                "unexpected_interval",
                ValidationStatus.FAIL,
                ValidationSeverity.ERROR,
                "Open-time differences are not multiples of the configured interval",
                affected_rows=len(unexpected_interval),
                sample_rows=unexpected_interval[: policy.sample_limit],
            )
        )

    timestamp_issue_names = {
        "non_monotonic_timestamp",
        "misaligned_open_time",
        "open_not_before_close",
        "invalid_close_time",
        "unexpected_interval",
    }
    if not any(check.check_name in timestamp_issue_names for check in checks):
        checks.append(_pass(context, "timestamps", "Timestamp order and interval semantics pass"))
    metrics["timestamp_errors"] = sum(
        check.affected_rows for check in checks if check.check_name in timestamp_issue_names
    )

    gap_metrics = _gap_metrics(open_times, context, interval_delta, policy.sample_limit)
    metrics.update(gap_metrics)
    missing_count = gap_metrics["number_of_missing_candles"]
    if missing_count:
        allowed = (
            gap_metrics["gap_percentage"] <= policy.allowed_missing_percentage
            and gap_metrics["largest_gap"] <= policy.maximum_consecutive_missing_intervals
        )
        checks.append(
            _result(
                context,
                "missing_interval",
                ValidationStatus.WARN if allowed else ValidationStatus.FAIL,
                ValidationSeverity.WARNING if allowed else ValidationSeverity.ERROR,
                f"Found {missing_count} missing expected candles classified as UNKNOWN_GAP",
                observed_value={
                    "count": missing_count,
                    "percentage": gap_metrics["gap_percentage"],
                    "largest_gap": gap_metrics["largest_gap"],
                    "classification": GapClassification.UNKNOWN_GAP,
                },
                expected_value={
                    "allowed_percentage": policy.allowed_missing_percentage,
                    "allowed_consecutive": policy.maximum_consecutive_missing_intervals,
                },
                affected_rows=missing_count,
                sample_rows=gap_metrics["sample_missing_timestamps"],
            )
        )
    else:
        checks.append(_pass(context, "gaps", "No missing candle intervals were detected"))

    ohlc_rules = {
        "high_below_open": lambda row: row["high"] < row["open"],
        "high_below_close": lambda row: row["high"] < row["close"],
        "high_below_low": lambda row: row["high"] < row["low"],
        "low_above_open": lambda row: row["low"] > row["open"],
        "low_above_close": lambda row: row["low"] > row["close"],
        "non_positive_price": lambda row: any(
            row[name] <= 0 for name in ("open", "high", "low", "close")
        ),
    }
    invalid_ohlc_rows: set[int] = set()
    for name, predicate in ohlc_rules.items():
        affected = [index for index, row in enumerate(rows) if predicate(row)]
        if affected:
            invalid_ohlc_rows.update(affected)
            checks.append(
                _result(
                    context,
                    name,
                    ValidationStatus.FAIL,
                    ValidationSeverity.CRITICAL,
                    f"OHLC rule failed: {name}",
                    observed_value=len(affected),
                    expected_value=0,
                    affected_rows=len(affected),
                    sample_rows=affected[: policy.sample_limit],
                )
            )
    metrics["invalid_ohlc"] = len(invalid_ohlc_rows)
    if invalid_ohlc_rows:
        checks.append(
            _result(
                context,
                "invalid_ohlc",
                ValidationStatus.FAIL,
                ValidationSeverity.CRITICAL,
                "One or more impossible OHLC relationships were detected",
                affected_rows=len(invalid_ohlc_rows),
                sample_rows=sorted(invalid_ohlc_rows)[: policy.sample_limit],
            )
        )
    else:
        checks.append(_pass(context, "ohlc", "Price positivity and OHLC relationships pass"))

    volume_rules = {
        "negative_base_volume": lambda row: row["base_volume"] < 0,
        "negative_quote_volume": lambda row: row["quote_volume"] < 0,
        "negative_taker_buy_base_volume": lambda row: row["taker_buy_base_volume"] < 0,
        "negative_taker_buy_quote_volume": lambda row: row["taker_buy_quote_volume"] < 0,
        "negative_trade_count": lambda row: row["trade_count"] < 0,
        "taker_buy_base_exceeds_volume": lambda row: (
            row["taker_buy_base_volume"] > row["base_volume"]
        ),
        "taker_buy_quote_exceeds_volume": lambda row: (
            row["taker_buy_quote_volume"] > row["quote_volume"]
        ),
        "positive_volume_without_trades": lambda row: (
            row["trade_count"] == 0 and (row["base_volume"] > 0 or row["quote_volume"] > 0)
        ),
        "zero_base_volume_with_activity": lambda row: (
            row["base_volume"] == 0
            and any(
                row[name] != 0
                for name in (
                    "quote_volume",
                    "trade_count",
                    "taker_buy_base_volume",
                    "taker_buy_quote_volume",
                )
            )
        ),
    }
    volume_error_rows: set[int] = set()
    for name, predicate in volume_rules.items():
        affected = [index for index, row in enumerate(rows) if predicate(row)]
        if affected:
            volume_error_rows.update(affected)
            checks.append(
                _result(
                    context,
                    name,
                    ValidationStatus.FAIL,
                    ValidationSeverity.ERROR,
                    f"Volume/trade-count rule failed: {name}",
                    observed_value=len(affected),
                    expected_value=0,
                    affected_rows=len(affected),
                    sample_rows=affected[: policy.sample_limit],
                )
            )
    metrics["volume_errors"] = len(volume_error_rows)
    if not volume_error_rows:
        checks.append(_pass(context, "volume", "Volume and trade-count relationships pass"))

    zero_indexes = [index for index, row in enumerate(rows) if row["base_volume"] == 0]
    zero_runs = _runs(zero_indexes)
    zero_percentage = len(zero_indexes) / len(rows) * 100.0 if rows else 0.0
    metrics["zero_volume_count"] = len(zero_indexes)
    metrics["zero_volume_percentage"] = zero_percentage
    metrics["consecutive_zero_volume_runs"] = [end - start + 1 for start, end in zero_runs]
    metrics["leading_zero_volume_run"] = (
        zero_runs[0][1] - zero_runs[0][0] + 1 if zero_runs and zero_runs[0][0] == 0 else 0
    )
    metrics["trailing_zero_volume_run"] = (
        zero_runs[-1][1] - zero_runs[-1][0] + 1
        if zero_runs and zero_runs[-1][1] == len(rows) - 1
        else 0
    )
    metrics["zero_volume_sample_timestamps"] = [
        open_times[index] for index in zero_indexes[: policy.sample_limit]
    ]
    if zero_indexes and zero_percentage > policy.zero_volume_warning_percentage:
        checks.append(
            _result(
                context,
                "zero_volume",
                ValidationStatus.WARN,
                ValidationSeverity.WARNING,
                (
                    f"Found {len(zero_indexes)} structurally valid zero-volume candles; "
                    "prevalence is a liquidity observation"
                ),
                observed_value={
                    "count": len(zero_indexes),
                    "percentage": zero_percentage,
                    "runs": metrics["consecutive_zero_volume_runs"],
                    "scope": "partition_observation",
                },
                expected_value={
                    "warning_above_percentage": policy.zero_volume_warning_percentage,
                    "failure_above_percentage": policy.zero_volume_failure_percentage,
                    "failure_scope": "deprecated_liquidity_metadata_only",
                    "minimum_observations": policy.zero_volume_percentage_min_observations,
                },
                affected_rows=len(zero_indexes),
                sample_rows=metrics["zero_volume_sample_timestamps"],
            )
        )

    # Repeated flat prices are suspicious only when the source reports actual
    # trading activity. A structurally valid no-trade candle is source truth
    # about liquidity and is already exposed by the zero-volume checks above.
    flat_run_lengths: list[int] = []
    no_trade_flat_run_lengths: list[int] = []
    current_flat_run = 0
    current_no_trade_flat_run = 0
    previous_flat_price: Decimal | None = None
    previous_no_trade_flat_price: Decimal | None = None
    for row in rows:
        is_flat = row["open"] == row["high"] == row["low"] == row["close"]
        is_no_trade = row["base_volume"] == 0 and all(
            row[name] == 0
            for name in (
                "quote_volume",
                "trade_count",
                "taker_buy_base_volume",
                "taker_buy_quote_volume",
            )
        )
        if (
            is_flat
            and not is_no_trade
            and (previous_flat_price is None or previous_flat_price == row["close"])
        ):
            current_flat_run += 1
            previous_flat_price = row["close"]
        elif is_flat and not is_no_trade:
            if current_flat_run:
                flat_run_lengths.append(current_flat_run)
            current_flat_run = 1
            previous_flat_price = row["close"]
        else:
            if current_flat_run:
                flat_run_lengths.append(current_flat_run)
            current_flat_run = 0
            previous_flat_price = None
        if (
            is_flat
            and is_no_trade
            and (
                previous_no_trade_flat_price is None or previous_no_trade_flat_price == row["close"]
            )
        ):
            current_no_trade_flat_run += 1
            previous_no_trade_flat_price = row["close"]
        elif is_flat and is_no_trade:
            if current_no_trade_flat_run:
                no_trade_flat_run_lengths.append(current_no_trade_flat_run)
            current_no_trade_flat_run = 1
            previous_no_trade_flat_price = row["close"]
        else:
            if current_no_trade_flat_run:
                no_trade_flat_run_lengths.append(current_no_trade_flat_run)
            current_no_trade_flat_run = 0
            previous_no_trade_flat_price = None
    if current_flat_run:
        flat_run_lengths.append(current_flat_run)
    if current_no_trade_flat_run:
        no_trade_flat_run_lengths.append(current_no_trade_flat_run)
    longest_flat_run = max(flat_run_lengths, default=0)
    metrics["longest_stale_flat_run"] = longest_flat_run
    metrics["longest_valid_no_trade_flat_run"] = max(no_trade_flat_run_lengths, default=0)
    if longest_flat_run >= policy.stale_flat_run_warning:
        failure = longest_flat_run >= policy.stale_flat_run_failure
        checks.append(
            _result(
                context,
                "stale_flat_run",
                ValidationStatus.FAIL if failure else ValidationStatus.WARN,
                ValidationSeverity.ERROR if failure else ValidationSeverity.WARNING,
                "A suspicious run of repeated flat candles was detected",
                observed_value=longest_flat_run,
                expected_value={
                    "warning": policy.stale_flat_run_warning,
                    "failure": policy.stale_flat_run_failure,
                },
                affected_rows=longest_flat_run,
            )
        )

    symbols = sorted({row["symbol"] for row in rows})
    sources = sorted({row["source"] for row in rows})
    identity_failure = False
    if len(symbols) > 1 or (context.symbol is not None and symbols != [context.symbol]):
        identity_failure = True
        checks.append(
            _result(
                context,
                "symbol_consistency",
                ValidationStatus.FAIL,
                ValidationSeverity.CRITICAL,
                "Partition contains an unexpected or mixed symbol identity",
                observed_value=symbols,
                expected_value=context.symbol,
                affected_rows=len(rows),
            )
        )
    if len(sources) > 1 or (context.source is not None and sources != [context.source]):
        identity_failure = True
        checks.append(
            _result(
                context,
                "source_consistency",
                ValidationStatus.FAIL,
                ValidationSeverity.CRITICAL,
                "Partition contains an unexpected or mixed source identity",
                observed_value=sources,
                expected_value=context.source,
                affected_rows=len(rows),
            )
        )
    if not identity_failure:
        checks.append(_pass(context, "identity", "Symbol and source identity are homogeneous"))

    now = datetime.now(UTC)
    invalid_ingestion = [
        index for index, row in enumerate(rows) if row["ingested_at"] < row["close_time"]
    ]
    future_ingestion = [
        index
        for index, row in enumerate(rows)
        if row["ingested_at"] > now + timedelta(seconds=policy.ingestion_future_tolerance_seconds)
    ]
    if invalid_ingestion:
        checks.append(
            _result(
                context,
                "ingestion_before_market_close",
                ValidationStatus.FAIL,
                ValidationSeverity.ERROR,
                "ingested_at precedes the represented candle close",
                affected_rows=len(invalid_ingestion),
                sample_rows=invalid_ingestion[: policy.sample_limit],
            )
        )
    if future_ingestion:
        checks.append(
            _result(
                context,
                "future_ingestion_timestamp",
                ValidationStatus.FAIL,
                ValidationSeverity.ERROR,
                "ingested_at is implausibly later than validator time",
                affected_rows=len(future_ingestion),
                sample_rows=future_ingestion[: policy.sample_limit],
            )
        )
    if not invalid_ingestion and not future_ingestion:
        checks.append(_pass(context, "ingestion_timestamp", "Ingestion timestamps are plausible"))

    out_of_partition: list[int] = []
    if context.range_start is not None and context.range_end is not None:
        start = context.range_start.astimezone(UTC)
        end = context.range_end.astimezone(UTC)
        out_of_partition = [
            index
            for index, timestamp in enumerate(open_times)
            if timestamp < start or timestamp >= end
        ]
    if out_of_partition:
        checks.append(
            _result(
                context,
                "partition_boundary",
                ValidationStatus.FAIL,
                ValidationSeverity.CRITICAL,
                "Rows fall outside the declared half-open partition range",
                affected_rows=len(out_of_partition),
                sample_rows=out_of_partition[: policy.sample_limit],
            )
        )
    else:
        checks.append(_pass(context, "partition_boundary", "Rows belong to the partition range"))

    closes: list[Decimal] = [row["close"] for row in rows]
    outliers = (
        _detect_outliers(closes, open_times, policy) if all(close > 0 for close in closes) else []
    )
    metrics["candidate_outliers"] = len(outliers)
    if outliers:
        checks.append(
            _result(
                context,
                "candidate_price_outlier",
                ValidationStatus.WARN,
                ValidationSeverity.WARNING,
                "Robust rolling median/MAD analysis flagged candidate price anomalies; "
                "rows retained",
                observed_value=len(outliers),
                expected_value=f"MAD score <= {policy.outlier_mad_threshold}",
                affected_rows=len(outliers),
                sample_rows=outliers[: policy.sample_limit],
            )
        )
    else:
        checks.append(_pass(context, "price_outliers", "No robust statistical outliers detected"))

    return validation
