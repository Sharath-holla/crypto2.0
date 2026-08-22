from __future__ import annotations

import json
import os
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_ai.phase7.config import (
    CORE_UNIVERSE_VERSION,
    EXPANSION_UNIVERSE_VERSION,
    UNIVERSE_VERSION,
    UniverseConfig,
    stable_hash,
)
from crypto_ai.phase7.registry import SymbolRecord, SymbolRegistry


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("universe timestamps must be timezone-aware")
    return value.astimezone(UTC)


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    ELIGIBLE_WITH_WARNING = "ELIGIBLE_WITH_WARNING"
    INELIGIBLE_DATA_QUALITY = "INELIGIBLE_DATA_QUALITY"
    INELIGIBLE_HISTORY = "INELIGIBLE_HISTORY"
    INELIGIBLE_LIQUIDITY = "INELIGIBLE_LIQUIDITY"
    INELIGIBLE_NOT_AVAILABLE = "INELIGIBLE_NOT_AVAILABLE"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SymbolDescriptor(_Frozen):
    symbol: str
    as_of: datetime
    source_max_time: datetime
    trailing_quote_volume: float = Field(ge=0)
    realized_volatility: float = Field(ge=0)
    trade_intensity: float = Field(ge=0)
    funding_variability: float | None = Field(default=None, ge=0)
    btc_beta: float | None = None
    btc_correlation: float | None = Field(default=None, ge=-1, le=1)
    history_days: float = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)
    gap_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    warnings: tuple[str, ...] = ()

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("descriptor symbol cannot be empty")
        return normalized

    @field_validator("as_of", "source_max_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_source_boundary(self) -> Self:
        if self.source_max_time >= self.as_of:
            raise ValueError("descriptor source_max_time must be strictly before as_of")
        return self


class EligibilityDecision(_Frozen):
    symbol: str
    as_of: datetime
    status: EligibilityStatus
    reasons: tuple[str, ...]
    descriptor: SymbolDescriptor | None = None


class UniverseMember(_Frozen):
    symbol: str
    selection_rank: int = Field(ge=1)
    liquidity_percentile: float = Field(ge=0, le=1)
    volatility_percentile: float = Field(ge=0, le=1)
    history_percentile: float = Field(ge=0, le=1)
    trailing_quote_volume: float
    realized_volatility: float
    history_days: float
    coverage_ratio: float
    eligibility_status: EligibilityStatus


class FrozenUniverse(_Frozen):
    version: Literal["core_universe_v1"] = CORE_UNIVERSE_VERSION
    universe_role: Literal["CORE_BENCHMARK"] = "CORE_BENCHMARK"
    registry_version: str
    registry_hash: str
    selection_cutoff: datetime
    selection_method: str
    members: tuple[UniverseMember, ...]
    exclusions: tuple[EligibilityDecision, ...]
    universe_hash: str
    prospective_holdout_status: Literal["LOCKED_UNUSED"] = "LOCKED_UNUSED"
    prospective_holdout_used: Literal[False] = False
    prospective_holdout_evaluation_authorized: Literal[False] = False

    @field_validator("selection_cutoff")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        symbols = [member.symbol for member in self.members]
        if len(symbols) != len(set(symbols)):
            raise ValueError("universe members must be unique")
        expected = universe_identity(
            self.registry_hash,
            self.selection_cutoff,
            self.selection_method,
            self.members,
            self.exclusions,
        )
        if expected != self.universe_hash:
            raise ValueError("universe hash does not match its contents")
        return self

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(member.symbol for member in self.members)


class ExpansionUniversePolicy(_Frozen):
    version: Literal["expansion_universe_v1"] = EXPANSION_UNIVERSE_VERSION
    definition_version: Literal["dual_universe_v2"] = UNIVERSE_VERSION
    core_universe_version: Literal["core_universe_v1"] = CORE_UNIVERSE_VERSION
    core_universe_hash: str
    as_of_rule: Literal["fold_train_end"] = "fold_train_end"
    selection_method: Literal["point_in_time_quality_then_coverage_liquidity_history"] = (
        "point_in_time_quality_then_coverage_liquidity_history"
    )
    minimum_history_days: int
    minimum_coverage_ratio: float
    minimum_trailing_quote_volume: float
    required_intervals: tuple[str, ...]
    expansion_max_symbols_per_fold: int
    total_max_symbols_per_fold: int
    age_bucket_edges_days: tuple[int, int, int]
    policy_hash: str
    prospective_holdout_status: Literal["LOCKED_UNUSED"] = "LOCKED_UNUSED"
    prospective_holdout_used: Literal[False] = False
    prospective_holdout_evaluation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.policy_hash != expansion_policy_identity(self):
            raise ValueError("expansion universe policy hash does not match its contents")
        return self


class FoldUniverseMember(_Frozen):
    fold_id: str
    symbol: str
    source: Literal["CORE", "EXPANSION"]
    available_from: datetime
    history_days_as_of_fold: float = Field(ge=0)
    age_bucket: str
    liquidity_as_of_fold: float | None = Field(default=None, ge=0)
    quality_status: str
    eligible: bool
    reason: str

    @field_validator("symbol")
    @classmethod
    def normalize_member_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("fold universe symbol cannot be empty")
        return normalized

    @field_validator("available_from")
    @classmethod
    def normalize_available_from(cls, value: datetime) -> datetime:
        return _utc(value)


class FoldActiveUniverse(_Frozen):
    definition_version: Literal["dual_universe_v2"] = UNIVERSE_VERSION
    research_view: Literal["CORE", "EXPANDING"]
    fold_id: str
    as_of: datetime
    core_universe_version: Literal["core_universe_v1"] = CORE_UNIVERSE_VERSION
    core_universe_hash: str
    expansion_policy_version: Literal["expansion_universe_v1"] = EXPANSION_UNIVERSE_VERSION
    expansion_policy_hash: str
    core_eligible_symbols: tuple[str, ...]
    expansion_eligible_symbols: tuple[str, ...]
    active_symbols: tuple[str, ...]
    members: tuple[FoldUniverseMember, ...]
    expansion_max_symbols_per_fold: int
    total_max_symbols_per_fold: int
    membership_hash: str
    prospective_holdout_status: Literal["LOCKED_UNUSED"] = "LOCKED_UNUSED"
    prospective_holdout_used: Literal[False] = False
    prospective_holdout_evaluation_authorized: Literal[False] = False

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_membership(self) -> Self:
        if len(self.active_symbols) != len(set(self.active_symbols)):
            raise ValueError("fold active symbols must be unique")
        if len(self.active_symbols) > self.total_max_symbols_per_fold:
            raise ValueError("fold active symbols exceed the configured total cap")
        if len(self.expansion_eligible_symbols) > self.expansion_max_symbols_per_fold:
            raise ValueError("fold expansion symbols exceed the configured expansion cap")
        expected = fold_membership_identity(self)
        if self.membership_hash != expected:
            raise ValueError("fold universe membership hash does not match its contents")
        return self


def latest_descriptors(
    descriptors: list[SymbolDescriptor], *, as_of: datetime
) -> dict[str, SymbolDescriptor]:
    cutoff = _utc(as_of)
    selected: dict[str, SymbolDescriptor] = {}
    for descriptor in descriptors:
        if descriptor.as_of > cutoff:
            continue
        previous = selected.get(descriptor.symbol)
        if previous is None or descriptor.as_of > previous.as_of:
            selected[descriptor.symbol] = descriptor
    return selected


def evaluate_eligibility(
    record: SymbolRecord,
    descriptor: SymbolDescriptor | None,
    *,
    as_of: datetime,
    config: UniverseConfig,
) -> EligibilityDecision:
    cutoff = _utc(as_of)
    reasons: list[str] = []
    if not record.exists_at(cutoff):
        return EligibilityDecision(
            symbol=record.symbol,
            as_of=cutoff,
            status=EligibilityStatus.INELIGIBLE_NOT_AVAILABLE,
            reasons=("symbol_not_point_in_time_available",),
        )
    if record.quote_asset != config.quote_asset or record.contract_type != config.contract_type:
        return EligibilityDecision(
            symbol=record.symbol,
            as_of=cutoff,
            status=EligibilityStatus.INELIGIBLE_NOT_AVAILABLE,
            reasons=("not_usdt_perpetual",),
        )
    if not set(config.required_intervals).issubset(record.available_intervals):
        return EligibilityDecision(
            symbol=record.symbol,
            as_of=cutoff,
            status=EligibilityStatus.INELIGIBLE_DATA_QUALITY,
            reasons=("required_interval_archive_coverage_missing",),
            descriptor=descriptor,
        )
    history_days = (cutoff - record.available_from).total_seconds() / 86_400
    if descriptor is None or history_days < config.minimum_history_days:
        return EligibilityDecision(
            symbol=record.symbol,
            as_of=cutoff,
            status=EligibilityStatus.INELIGIBLE_HISTORY,
            reasons=("insufficient_point_in_time_history",),
            descriptor=descriptor,
        )
    if descriptor.history_days < config.minimum_history_days:
        return EligibilityDecision(
            symbol=record.symbol,
            as_of=cutoff,
            status=EligibilityStatus.INELIGIBLE_HISTORY,
            reasons=("descriptor_history_below_minimum",),
            descriptor=descriptor,
        )
    if (
        descriptor.coverage_ratio < config.minimum_coverage_ratio
        or descriptor.duplicate_count
        or descriptor.invalid_count
    ):
        return EligibilityDecision(
            symbol=record.symbol,
            as_of=cutoff,
            status=EligibilityStatus.INELIGIBLE_DATA_QUALITY,
            reasons=("coverage_or_integrity_gate_failed",),
            descriptor=descriptor,
        )
    if descriptor.trailing_quote_volume < config.minimum_trailing_quote_volume:
        return EligibilityDecision(
            symbol=record.symbol,
            as_of=cutoff,
            status=EligibilityStatus.INELIGIBLE_LIQUIDITY,
            reasons=("trailing_liquidity_below_minimum",),
            descriptor=descriptor,
        )
    if descriptor.coverage_ratio < config.warning_coverage_ratio:
        reasons.append("coverage_below_warning_target")
    reasons.extend(descriptor.warnings)
    return EligibilityDecision(
        symbol=record.symbol,
        as_of=cutoff,
        status=(EligibilityStatus.ELIGIBLE_WITH_WARNING if reasons else EligibilityStatus.ELIGIBLE),
        reasons=tuple(sorted(set(reasons))),
        descriptor=descriptor,
    )


def fold_local_eligibility(
    registry: SymbolRegistry,
    descriptors: list[SymbolDescriptor],
    *,
    train_end: datetime,
    config: UniverseConfig,
    candidate_symbols: set[str] | None = None,
) -> tuple[EligibilityDecision, ...]:
    point_in_time = latest_descriptors(descriptors, as_of=train_end)
    candidates = (
        {symbol.upper() for symbol in candidate_symbols}
        if candidate_symbols is not None
        else {record.symbol for record in registry.records}
    )
    return tuple(
        evaluate_eligibility(
            record,
            point_in_time.get(record.symbol),
            as_of=train_end,
            config=config,
        )
        for record in registry.records
        if record.symbol in candidates
    )


def _percentile(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values, key=lambda symbol: (values[symbol], symbol))
    denominator = max(1, len(ordered) - 1)
    return {symbol: index / denominator for index, symbol in enumerate(ordered)}


def universe_identity(
    registry_hash: str,
    selection_cutoff: datetime,
    selection_method: str,
    members: tuple[UniverseMember, ...],
    exclusions: tuple[EligibilityDecision, ...],
) -> str:
    return stable_hash(
        {
            "version": CORE_UNIVERSE_VERSION,
            "universe_role": "CORE_BENCHMARK",
            "registry_hash": registry_hash,
            "selection_cutoff": _utc(selection_cutoff),
            "selection_method": selection_method,
            "members": [member.model_dump(mode="json") for member in members],
            "exclusions": [item.model_dump(mode="json") for item in exclusions],
        }
    )


def select_core_universe(
    registry: SymbolRegistry,
    descriptors: list[SymbolDescriptor],
    *,
    selection_cutoff: datetime,
    config: UniverseConfig,
) -> FrozenUniverse:
    cutoff = _utc(selection_cutoff)
    decisions = fold_local_eligibility(
        registry,
        descriptors,
        train_end=cutoff,
        config=config,
        candidate_symbols={
            record.symbol for record in registry.records if record.available_from < cutoff
        },
    )
    eligible = [
        decision
        for decision in decisions
        if decision.status in {EligibilityStatus.ELIGIBLE, EligibilityStatus.ELIGIBLE_WITH_WARNING}
        and decision.descriptor is not None
    ]
    if len(eligible) < min(config.core_target_size, len(registry.records)):
        raise ValueError(
            f"Only {len(eligible)} eligible symbols exist for core size {config.core_target_size}"
        )
    descriptor_map = {item.symbol: item.descriptor for item in eligible}
    liquidity = _percentile(
        {symbol: descriptor.trailing_quote_volume for symbol, descriptor in descriptor_map.items()}
    )
    volatility = _percentile(
        {symbol: descriptor.realized_volatility for symbol, descriptor in descriptor_map.items()}
    )
    history = _percentile(
        {symbol: descriptor.history_days for symbol, descriptor in descriptor_map.items()}
    )
    buckets: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    for symbol in descriptor_map:
        key = (
            min(2, int(liquidity[symbol] * 3)),
            min(2, int(volatility[symbol] * 3)),
            min(2, int(history[symbol] * 3)),
        )
        buckets[key].append(symbol)
    for symbols in buckets.values():
        symbols.sort(
            key=lambda symbol: (
                -descriptor_map[symbol].coverage_ratio,
                -descriptor_map[symbol].history_days,
                symbol,
            )
        )
    chosen: list[str] = []
    for anchor in config.required_anchor_symbols:
        if anchor not in descriptor_map:
            raise ValueError(f"Required anchor {anchor} is not point-in-time eligible")
        chosen.append(anchor)
    keys = sorted(buckets)
    while len(chosen) < config.core_target_size:
        progress = False
        for key in keys:
            while buckets[key] and buckets[key][0] in chosen:
                buckets[key].pop(0)
            if buckets[key] and len(chosen) < config.core_target_size:
                chosen.append(buckets[key].pop(0))
                progress = True
        if not progress:
            break
    if len(chosen) != config.core_target_size:
        raise ValueError("Systematic stratified selection could not fill the core universe")
    decision_map = {item.symbol: item for item in eligible}
    members = tuple(
        UniverseMember(
            symbol=symbol,
            selection_rank=index,
            liquidity_percentile=liquidity[symbol],
            volatility_percentile=volatility[symbol],
            history_percentile=history[symbol],
            trailing_quote_volume=descriptor_map[symbol].trailing_quote_volume,
            realized_volatility=descriptor_map[symbol].realized_volatility,
            history_days=descriptor_map[symbol].history_days,
            coverage_ratio=descriptor_map[symbol].coverage_ratio,
            eligibility_status=decision_map[symbol].status,
        )
        for index, symbol in enumerate(chosen, start=1)
    )
    exclusions = tuple(
        sorted(
            (item for item in decisions if item.symbol not in chosen), key=lambda item: item.symbol
        )
    )
    method = "core_point_in_time_quality_gate_then_liquidity_volatility_age_stratified_round_robin"
    identity = universe_identity(registry.registry_hash, cutoff, method, members, exclusions)
    return FrozenUniverse(
        registry_version=registry.version,
        registry_hash=registry.registry_hash,
        selection_cutoff=cutoff,
        selection_method=method,
        members=members,
        exclusions=exclusions,
        universe_hash=identity,
    )


def select_pilot_universe(
    registry: SymbolRegistry,
    descriptors: list[SymbolDescriptor],
    *,
    selection_cutoff: datetime,
    config: UniverseConfig,
) -> FrozenUniverse:
    """Backward-compatible name for the frozen core benchmark selector."""

    return select_core_universe(
        registry,
        descriptors,
        selection_cutoff=selection_cutoff,
        config=config,
    )


def expansion_policy_identity(policy: ExpansionUniversePolicy) -> str:
    return stable_hash(policy.model_dump(mode="json", exclude={"policy_hash"}))


def build_expansion_policy(
    core_universe: FrozenUniverse,
    config: UniverseConfig,
) -> ExpansionUniversePolicy:
    payload = {
        "version": EXPANSION_UNIVERSE_VERSION,
        "definition_version": UNIVERSE_VERSION,
        "core_universe_version": core_universe.version,
        "core_universe_hash": core_universe.universe_hash,
        "as_of_rule": config.expansion_as_of,
        "selection_method": "point_in_time_quality_then_coverage_liquidity_history",
        "minimum_history_days": config.minimum_history_days,
        "minimum_coverage_ratio": config.minimum_coverage_ratio,
        "minimum_trailing_quote_volume": config.minimum_trailing_quote_volume,
        "required_intervals": config.required_intervals,
        "expansion_max_symbols_per_fold": config.expansion_max_symbols_per_fold,
        "total_max_symbols_per_fold": config.total_max_symbols_per_fold,
        "age_bucket_edges_days": config.age_bucket_edges_days,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "prospective_holdout_evaluation_authorized": False,
    }
    return ExpansionUniversePolicy(**payload, policy_hash=stable_hash(payload))


def cold_start_age_bucket(
    history_days: float,
    edges: tuple[int, int, int],
) -> str:
    first, second, third = edges
    if history_days < first:
        return f"LT_{first}_DAYS"
    if history_days < second:
        return f"DAYS_{first}_{second - 1}"
    if history_days < third:
        return f"DAYS_{second}_{third - 1}"
    return f"DAYS_{third}_PLUS"


def fold_membership_identity(membership: FoldActiveUniverse) -> str:
    return stable_hash(membership.model_dump(mode="json", exclude={"membership_hash"}))


def _is_eligible(decision: EligibilityDecision) -> bool:
    return decision.status in {
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.ELIGIBLE_WITH_WARNING,
    }


def select_fold_active_universe(
    registry: SymbolRegistry,
    descriptors: list[SymbolDescriptor],
    *,
    fold_id: str,
    train_end: datetime,
    core_universe: FrozenUniverse,
    expansion_policy: ExpansionUniversePolicy,
    config: UniverseConfig,
    research_view: Literal["CORE", "EXPANDING"],
) -> FoldActiveUniverse:
    """Apply frozen policy with only descriptors sourced before this fold's TRAIN end."""

    cutoff = _utc(train_end)
    registry_map = registry.by_symbol()
    point_in_time = latest_descriptors(descriptors, as_of=cutoff)
    core_decisions = fold_local_eligibility(
        registry,
        descriptors,
        train_end=cutoff,
        config=config,
        candidate_symbols=set(core_universe.symbols),
    )
    core_eligible = tuple(sorted(item.symbol for item in core_decisions if _is_eligible(item)))

    # Symbols not evidenced strictly before the fold cutoff are deliberately
    # absent rather than reported as known future exclusions.
    expansion_candidates = {
        record.symbol
        for record in registry.records
        if record.symbol not in core_universe.symbols
        and record.available_from >= core_universe.selection_cutoff
        and record.available_from < cutoff
    }
    expansion_decisions = fold_local_eligibility(
        registry,
        descriptors,
        train_end=cutoff,
        config=config,
        candidate_symbols=expansion_candidates,
    )
    ranked_expansion = sorted(
        (
            item
            for item in expansion_decisions
            if _is_eligible(item) and item.descriptor is not None
        ),
        key=lambda item: (
            item.status is EligibilityStatus.ELIGIBLE_WITH_WARNING,
            -item.descriptor.coverage_ratio,  # type: ignore[union-attr]
            -item.descriptor.trailing_quote_volume,  # type: ignore[union-attr]
            -item.descriptor.history_days,  # type: ignore[union-attr]
            item.symbol,
        ),
    )
    available_slots = max(0, config.total_max_symbols_per_fold - len(core_eligible))
    expansion_limit = min(config.expansion_max_symbols_per_fold, available_slots)
    selected_expansion = (
        tuple(item.symbol for item in ranked_expansion[:expansion_limit])
        if config.enable_expansion and research_view == "EXPANDING"
        else ()
    )
    selected_expansion_set = set(selected_expansion)
    decision_by_symbol = {item.symbol: item for item in (*core_decisions, *expansion_decisions)}
    source_by_symbol = {
        **{symbol: "CORE" for symbol in core_universe.symbols},
        **{symbol: "EXPANSION" for symbol in expansion_candidates},
    }
    members: list[FoldUniverseMember] = []
    for symbol in sorted(source_by_symbol):
        source = source_by_symbol[symbol]
        decision = decision_by_symbol[symbol]
        record = registry_map[symbol]
        descriptor = point_in_time.get(symbol)
        gate_eligible = _is_eligible(decision)
        selected = gate_eligible and (
            source == "CORE" or (research_view == "EXPANDING" and symbol in selected_expansion_set)
        )
        if selected:
            reason = "eligible"
        elif source == "EXPANSION" and gate_eligible and research_view == "CORE":
            reason = "core_benchmark_excludes_expansion_symbols"
        elif source == "EXPANSION" and gate_eligible:
            reason = "expansion_fold_cap"
        else:
            reason = ";".join(decision.reasons) or decision.status.value.lower()
        history_days = (cutoff - record.available_from).total_seconds() / 86_400
        members.append(
            FoldUniverseMember(
                fold_id=fold_id,
                symbol=symbol,
                source=source,  # type: ignore[arg-type]
                available_from=record.available_from,
                history_days_as_of_fold=history_days,
                age_bucket=cold_start_age_bucket(history_days, config.age_bucket_edges_days),
                liquidity_as_of_fold=(
                    descriptor.trailing_quote_volume if descriptor is not None else None
                ),
                quality_status=decision.status.value,
                eligible=selected,
                reason=reason,
            )
        )
    active = tuple(sorted((*core_eligible, *selected_expansion)))
    payload = {
        "definition_version": UNIVERSE_VERSION,
        "research_view": research_view,
        "fold_id": fold_id,
        "as_of": cutoff,
        "core_universe_version": core_universe.version,
        "core_universe_hash": core_universe.universe_hash,
        "expansion_policy_version": expansion_policy.version,
        "expansion_policy_hash": expansion_policy.policy_hash,
        "core_eligible_symbols": core_eligible,
        "expansion_eligible_symbols": selected_expansion,
        "active_symbols": active,
        "members": tuple(members),
        "expansion_max_symbols_per_fold": config.expansion_max_symbols_per_fold,
        "total_max_symbols_per_fold": config.total_max_symbols_per_fold,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "prospective_holdout_evaluation_authorized": False,
    }
    draft = FoldActiveUniverse.model_construct(**payload, membership_hash="")
    return FoldActiveUniverse(**payload, membership_hash=fold_membership_identity(draft))


def research_universe_identity(
    core_universe: FrozenUniverse,
    expansion_policy: ExpansionUniversePolicy,
    acquisition_symbols: tuple[str, ...],
) -> str:
    return stable_hash(
        {
            "definition_version": UNIVERSE_VERSION,
            "core_universe_hash": core_universe.universe_hash,
            "expansion_policy_hash": expansion_policy.policy_hash,
            "acquisition_symbols": acquisition_symbols,
        }
    )


def write_universe(path: Path, universe: FrozenUniverse) -> Path:
    path = path.resolve()
    payload = json.dumps(universe.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise FileExistsError(f"Refusing to overwrite different frozen universe: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def read_universe(path: Path) -> FrozenUniverse:
    return FrozenUniverse.model_validate(json.loads(path.read_text(encoding="utf-8")))


def write_expansion_policy(path: Path, policy: ExpansionUniversePolicy) -> Path:
    path = path.resolve()
    payload = json.dumps(policy.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise FileExistsError(f"Refusing to overwrite different expansion policy: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def read_expansion_policy(path: Path) -> ExpansionUniversePolicy:
    return ExpansionUniversePolicy.model_validate(json.loads(path.read_text(encoding="utf-8")))
