"""Regression tests: only genuine eligibility failures become INELIGIBLE.

Any other exception inside model fitting or evaluation is a defect and must
propagate (fail closed) instead of being silently recorded as INELIGIBLE and
checkpointed COMPLETE, which would have made resume skip the experiment forever.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pytest

from crypto_ai.phase5.folds import FoldPlan
from crypto_ai.phase7.config import Phase7Config
from crypto_ai.phase7.folds import IneligibleFoldError, MultiAssetFoldData
from crypto_ai.phase7.models import _fit, symbol_balanced_weights
from crypto_ai.phase7.training import ExperimentSpec, run_phase7_training

_US = 1_000_000


def _fold_table(rows: int = 3) -> pa.Table:
    base = datetime(2022, 1, 1, tzinfo=UTC)
    return pa.table(
        {
            "symbol": ["BTCUSDT"] * rows,
            "feature_time": pa.array(
                [int(base.timestamp() * _US) + step * 300 * _US for step in range(rows)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "entry_time": pa.array(
                [int(base.timestamp() * _US) + (step + 1) * 300 * _US for step in range(rows)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "label_end_time": pa.array(
                [int(base.timestamp() * _US) + (step + 13) * 300 * _US for step in range(rows)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "horizon_minutes": [60] * rows,
            "raw_future_return": [0.001, -0.002, 0.003],
            "normalized_future_return": [0.1, -0.2, 0.3],
            "ex_ante_volatility_scale": [0.01] * rows,
            "f1": [1.0, 2.0, 3.0],
            "btc_return_4h": [0.0, 0.0, 0.0],
            "relative_strength_vs_btc": [0.0, 0.0, 0.0],
            "mfe_long": [0.01, 0.01, 0.01],
            "mae_long": [0.005, 0.005, 0.005],
            "cross_sectional_context_scope": ["FOLD_ACTIVE_SYMBOLS"] * rows,
        }
    )


def _fold_data(tmp_path: Path) -> MultiAssetFoldData:
    plan = FoldPlan(
        fold_id="fold-000-test",
        index=0,
        train_start=datetime(2020, 1, 1, tzinfo=UTC),
        train_end=datetime(2022, 1, 1, tzinfo=UTC),
        validation_start=datetime(2022, 1, 1, tzinfo=UTC),
        validation_end=datetime(2022, 4, 1, tzinfo=UTC),
        calibration_start=datetime(2022, 4, 1, tzinfo=UTC),
        calibration_end=datetime(2022, 7, 1, tzinfo=UTC),
        test_start=datetime(2022, 7, 1, tzinfo=UTC),
        test_end=datetime(2022, 10, 1, tzinfo=UTC),
    )
    table = _fold_table()
    return MultiAssetFoldData(
        plan=plan,
        train=table,
        validation=table,
        calibration_a=table,
        calibration_b=table,
        _test=table,
        eligibility_manifest={
            "eligible_symbols": ["BTCUSDT"],
            "core_eligible_symbols": ["BTCUSDT"],
            "expansion_eligible_symbols": [],
            "fold_membership_hash": "test-membership-hash",
        },
        cluster_mapping={"BTCUSDT": 0},
        liquidity_tiers={"BTCUSDT": "HIGH_LIQUIDITY"},
        age_buckets={"BTCUSDT": "middle"},
        research_view="CORE",
        report={"boundaries": plan.to_dict()},
    )


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "gold" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"classification": "RETROSPECTIVE_MULTI_ASSET_RESEARCH",'
        ' "prospective_holdout_status": "LOCKED_UNUSED",'
        ' "prospective_holdout_used": false,'
        ' "prospective_holdout_evaluation_authorized": false,'
        ' "july_2026_used": false,'
        ' "partition_files": [],'
        ' "feature_groups": {"A6": ["f1"]},'
        ' "dataset_id": "gold-test"}',
        encoding="utf-8",
    )
    return path


def _patch_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    fit_error: Exception,
) -> tuple[Path, Path, list[int]]:
    fit_calls: list[int] = []
    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")
    manifest = _manifest(tmp_path)
    checkpoint_root = tmp_path / "checkpoints"
    run_root = tmp_path / "run"

    def fake_manifest(_: Path) -> dict[str, object]:
        import json

        return json.loads(manifest.read_text(encoding="utf-8"))

    def fake_plan_folds(*_args: object, **_kwargs: object) -> tuple[FoldPlan, ...]:
        return (_fold_data(tmp_path).plan,)

    def fake_specs(_: Phase7Config) -> tuple[ExperimentSpec, ...]:
        return (
            ExperimentSpec(
                name="architecture-G0-A6-60m-raw",
                architecture="G0",
                feature_group="A6",
                horizon_minutes=60,
                target_type="raw",
                symbol_balanced=True,
            ),
        )

    def fake_load_rows(*_args: object, **_kwargs: object) -> pa.Table:
        return _fold_table()

    def fake_slice(*_args: object, **_kwargs: object) -> MultiAssetFoldData:
        return _fold_data(tmp_path)

    def fake_fit(*_args: object, **_kwargs: object) -> object:
        fit_calls.append(1)
        raise fit_error

    monkeypatch.setattr("crypto_ai.phase7.training._load_gold_manifest", fake_manifest)
    monkeypatch.setattr("crypto_ai.phase7.training.plan_folds", fake_plan_folds)
    monkeypatch.setattr("crypto_ai.phase7.training.phase7_experiment_specs", fake_specs)
    monkeypatch.setattr("crypto_ai.phase7.training._load_fold_rows", fake_load_rows)
    monkeypatch.setattr("crypto_ai.phase7.training.slice_multiasset_fold", fake_slice)
    monkeypatch.setattr("crypto_ai.phase7.training.fit_architecture", fake_fit)
    return checkpoint_root, run_root, fit_calls


def test_data_defect_during_fit_propagates_and_is_never_ineligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain ValueError from model fitting is a defect: it must crash loudly."""
    checkpoint_root, run_root, _fit_calls = _patch_harness(
        monkeypatch, tmp_path, fit_error=ValueError("defect: non-finite predictions")
    )
    config = Phase7Config()
    registry = _synthetic_registry()
    with pytest.raises(ValueError, match="non-finite predictions"):
        run_phase7_training(
            config,
            gold_manifest_path=_manifest(tmp_path),
            registry=registry.registry,
            universe=registry.universe,
            expansion_policy=registry.policy,
            descriptors=registry.descriptors,
            checkpoint_store=registry.store(checkpoint_root),
            run_root=run_root,
            resume=False,
        )
    # The failed experiment must NOT be checkpointed as complete.
    checkpointed = [
        path for path in checkpoint_root.rglob("*") if path.suffix == ".json" and path.is_file()
    ]
    assert checkpointed == []


def test_eligibility_failure_records_ineligible_and_resume_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """IneligibleFoldError is recorded INELIGIBLE and skipped on resume."""
    checkpoint_root, run_root, fit_calls = _patch_harness(
        monkeypatch,
        tmp_path,
        fit_error=IneligibleFoldError("G0 produced no eligible estimators"),
    )
    config = Phase7Config()
    registry = _synthetic_registry()
    first = run_phase7_training(
        config,
        gold_manifest_path=_manifest(tmp_path),
        registry=registry.registry,
        universe=registry.universe,
        expansion_policy=registry.policy,
        descriptors=registry.descriptors,
        checkpoint_store=registry.store(checkpoint_root),
        run_root=run_root,
        resume=False,
    )
    assert first["completed_reports"] == 0
    assert first["ineligible_reports"] == 2  # CORE + EXPANDING views
    assert len(fit_calls) == 2

    second = run_phase7_training(
        config,
        gold_manifest_path=_manifest(tmp_path),
        registry=registry.registry,
        universe=registry.universe,
        expansion_policy=registry.policy,
        descriptors=registry.descriptors,
        checkpoint_store=registry.store(checkpoint_root),
        run_root=run_root,
        resume=True,
    )
    # Resume reloads the INELIGIBLE reports from the checkpoints instead of
    # rerunning the experiments (fit is never invoked a second time).
    assert second["completed_reports"] == 0
    assert second["ineligible_reports"] == 2
    assert len(fit_calls) == 2


def test_symbol_balanced_weights_empty_raises_ineligible() -> None:
    with pytest.raises(IneligibleFoldError):
        symbol_balanced_weights([])  # type: ignore[arg-type]


def test_empty_lgbm_rows_raise_ineligible() -> None:
    import numpy as np

    from crypto_ai.phase7.config import ModelConfig

    with pytest.raises(IneligibleFoldError):
        _fit(
            np.asarray([], dtype=np.float64).reshape(0, 1),
            np.asarray([], dtype=np.float64),
            np.asarray([], dtype=np.float64).reshape(0, 1),
            np.asarray([], dtype=np.float64),
            config=ModelConfig(
                n_estimators=20,
                early_stopping_rounds=5,
                min_child_samples=5,
                minimum_train_rows_per_coin=100,
                minimum_validation_rows_per_coin=20,
                minimum_calibration_rows_per_coin=20,
            ),
            model_threads=1,
            sample_weight=None,
        )


def test_ineligible_fold_error_is_value_error_subclass() -> None:
    assert issubclass(IneligibleFoldError, ValueError)


class _RegistryHarness:
    def __init__(self) -> None:
        from crypto_ai.phase7.config import UniverseConfig
        from crypto_ai.phase7.fixtures import (
            fixture_universe_config,
            synthetic_descriptors,
            synthetic_registry,
        )
        from crypto_ai.phase7.universe import build_expansion_policy, select_core_universe

        self.registry = synthetic_registry()
        universe_config: UniverseConfig = fixture_universe_config()
        self.universe = select_core_universe(
            self.registry,
            synthetic_descriptors(as_of=universe_config.selection_cutoff),
            selection_cutoff=universe_config.selection_cutoff,
            config=universe_config,
        )
        self.policy = build_expansion_policy(self.universe, universe_config)
        self.descriptors = synthetic_descriptors(as_of=universe_config.selection_cutoff)

    def store(self, root: Path):
        from crypto_ai.phase7.artifacts import CheckpointStore

        return CheckpointStore(root, "audit-test-run")


def _synthetic_registry() -> _RegistryHarness:
    return _RegistryHarness()