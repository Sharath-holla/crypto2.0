from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Any

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
_HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class VersionCompatibility(StrEnum):
    EXACT = "EXACT"
    BACKWARD_COMPATIBLE = "BACKWARD_COMPATIBLE"
    BREAKING = "BREAKING"


class ContractConflict(ValueError):
    """Raised when one contract identity is assigned conflicting schemas."""


@dataclass(frozen=True, order=True, slots=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        if min(self.major, self.minor, self.patch) < 0:
            raise ValueError("semantic-version components cannot be negative")

    @classmethod
    def parse(cls, value: str) -> SemanticVersion:
        parts = value.split(".")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError(f"invalid semantic version: {value!r}")
        return cls(*(int(part) for part in parts))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class ContractDescriptor:
    name: str
    version: SemanticVersion
    schema_sha256: str
    owner: str

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"invalid contract name: {self.name!r}")
        if not _HEX_64_PATTERN.fullmatch(self.schema_sha256):
            raise ValueError("schema_sha256 must be a lowercase SHA-256 digest")
        if not self.owner.strip():
            raise ValueError("contract owner is required")

    @property
    def identity(self) -> str:
        return f"{self.name}@{self.version}"


class ContractRegistry:
    """In-memory definition registry; it performs no discovery or network access."""

    def __init__(self) -> None:
        self._contracts: dict[tuple[str, SemanticVersion], ContractDescriptor] = {}

    def register(self, descriptor: ContractDescriptor) -> ContractDescriptor:
        key = (descriptor.name, descriptor.version)
        existing = self._contracts.get(key)
        if existing is not None and existing != descriptor:
            raise ContractConflict(f"conflicting definition for {descriptor.identity}")
        self._contracts[key] = descriptor
        return descriptor

    def resolve(self, name: str, *, major: int | None = None) -> ContractDescriptor:
        candidates = [
            descriptor
            for (registered_name, version), descriptor in self._contracts.items()
            if registered_name == name and (major is None or version.major == major)
        ]
        if not candidates:
            suffix = "" if major is None else f" major={major}"
            raise KeyError(f"unknown contract {name!r}{suffix}")
        return max(candidates, key=lambda item: item.version)

    def descriptors(self) -> tuple[ContractDescriptor, ...]:
        return tuple(sorted(self._contracts.values(), key=lambda item: (item.name, item.version)))


def assess_version_change(
    previous: ContractDescriptor, current: ContractDescriptor
) -> VersionCompatibility:
    if previous.name != current.name:
        return VersionCompatibility.BREAKING
    if previous == current:
        return VersionCompatibility.EXACT
    if current.version <= previous.version or current.version.major != previous.version.major:
        return VersionCompatibility.BREAKING
    return VersionCompatibility.BACKWARD_COMPATIBLE


def _canonical(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(item) for item in value), key=repr)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetimes must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical payloads cannot contain non-finite floats")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical(value),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
