"""Additive, side-effect-free contracts for future system boundaries.

Nothing in this package performs exchange, account, cloud, or model-training I/O.
Phase 7 scientific modules do not import this package.
"""

from crypto_ai.contracts.baseline import PHASE7_APPROVED_BASELINE
from crypto_ai.contracts.events import EventEnvelope
from crypto_ai.contracts.execution import DisabledExecutionAdapter, ExecutionAdapter
from crypto_ai.contracts.models import ModelContract, PredictionEnvelope
from crypto_ai.contracts.versioning import ContractDescriptor, ContractRegistry, SemanticVersion

__all__ = [
    "PHASE7_APPROVED_BASELINE",
    "ContractDescriptor",
    "ContractRegistry",
    "DisabledExecutionAdapter",
    "EventEnvelope",
    "ExecutionAdapter",
    "ModelContract",
    "PredictionEnvelope",
    "SemanticVersion",
]
