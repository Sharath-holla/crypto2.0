from __future__ import annotations

import json
import subprocess
import sys
import weakref
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7 import artifacts, training
from crypto_ai.phase7.artifacts import atomic_json
from crypto_ai.phase7.benchmark_one_spec import benchmark_plan
from crypto_ai.phase7.config import Phase7Config, load_phase7_config, stable_hash
from crypto_ai.phase7.fixtures import synthetic_descriptors
from crypto_ai.phase7.gold_validation import (
    GoldValidationError,
    production_feature_columns,
    production_gold_schema,
    validate_phase7_gold,
)
from crypto_ai.phase7.phase7a import enumerate_specs, primary_specs, select_one_spec
from crypto_ai.phase7.preflight import _validated_gold_report
from crypto_ai.phase7.prepared_cache import (
    PreparedCacheCapacityError,
    PreparedDataCache,
    capacity_projection,
)
from tests.phase7.test_gold_validation import _gold_fixture
from tests.phase7.test_prepared_cache import _fixture
from tests.phase7.test_training_error_classification import (
    _fold_data,
    _patch_harness,
    _synthetic_registry,
)

ROOT = Path(__file__).resolve().parents[2]


def canonical():
    return load_phase7_config(ROOT / "configs/phase7/research_core20_primary_v1.toml")


def test_exact_canonical_spec_cartesian_product_and_deferred_partition():
    config = canonical()
    result = enumerate_specs(config)
    assert result["counts"] == {"PRIMARY_A6": 48, "DEFERRED_ABLATIONS": 6, "DEFERRED_HTF": 4}
    assert result["total"] == 58
    specs = primary_specs(config)
    assert len({s.name for s in specs}) == 48
    assert {s.name for s in specs} == {
        f"architecture-{variant}-A6-{horizon}m-{target}"
        for variant in ("G0", "C0", "P0", "H0", "G0-symbol-id", "G0-unbalanced")
        for horizon in (15, 30, 60, 120)
        for target in ("raw", "volatility_normalized")
    }
    assert len({row["spec_id"] for row in result["specs"]}) == 58
    for horizon in (15, 30, 60, 120):
        for target in ("raw", "volatility_normalized"):
            variants = {
                (s.architecture, s.symbol_balanced, s.explicit_symbol_id)
                for s in specs
                if s.horizon_minutes == horizon and s.target_type == target
            }
            assert variants == {
                ("G0", True, False),
                ("C0", True, False),
                ("P0", False, False),
                ("H0", True, False),
                ("G0", True, True),
                ("G0", False, False),
            }


@pytest.mark.parametrize(
    "spec_id", ["unknown", "feature-ablation-G0-A0-60m-raw", "htf-control-G0-BASE-60m-raw"]
)
def test_benchmark_rejects_unknown_and_deferred(spec_id):
    with pytest.raises(ValueError, match="unknown or deferred"):
        select_one_spec(canonical(), spec_id)


def test_exact_one_plan_is_isolated_and_config_unchanged(tmp_path):
    config = canonical()
    before = config.configuration_hash
    plan = benchmark_plan(config, primary_specs(config)[0].name, tmp_path / "isolated")
    assert plan["spec_count"] == plan["fold_count"] == 1
    assert plan["status"] == "BENCHMARK_ONLY"
    assert plan["canonical_fold_complete"] is False
    assert plan["canonical_primary_run_complete"] is False
    assert plan["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert config.configuration_hash == before
    with pytest.raises(ValueError, match="overlaps"):
        benchmark_plan(config, primary_specs(config)[0].name, config.paths.gold_root)
    assert len(training.phase7_experiment_specs(config)) == 58


@pytest.mark.parametrize("invocation", ["script", "module", "installed-module"])
def test_lightning_help_imports_without_script_package_path(invocation, tmp_path):
    target = {
        "script": [str(ROOT / "scripts/run_phase7a_lightning.py")],
        "module": ["-m", "scripts.run_phase7a_lightning"],
        "installed-module": ["-m", "crypto_ai.phase7.lightning"],
    }[invocation]
    result = subprocess.run(
        [sys.executable, *target, "--help"],
        cwd=ROOT if invocation == "module" else tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--stage" in result.stdout


def test_rebuild_publish_opens_on_same_object_and_exact_float64(tmp_path):
    _, fold, prepared, identity = _fixture()
    cache = PreparedDataCache(tmp_path, "rebuild")
    cache.write(identity, fold, prepared)
    loaded = cache.open_published(identity, fold.plan)
    assert loaded.prepared.model_inputs.train_x.dtype == np.float64
    assert np.array_equal(loaded.prepared.model_inputs.train_x, prepared.model_inputs.train_x)


def test_runner_rebuild_reaches_fit_without_false_cache_miss(tmp_path, monkeypatch):
    cp, root, calls = _patch_harness(monkeypatch, tmp_path, fit_error=ValueError("fit sentinel"))
    monkeypatch.setenv("PHASE7_CACHE_MODE", "rebuild")
    monkeypatch.setenv("PHASE7_CACHE_ROOT", str(tmp_path / "cache"))
    context = _synthetic_registry()
    with pytest.raises(ValueError, match="fit sentinel"):
        training.run_phase7_training(
            Phase7Config(),
            gold_manifest_path=tmp_path / "gold/manifest.json",
            registry=context.registry,
            universe=context.universe,
            expansion_policy=context.policy,
            descriptors=context.descriptors,
            checkpoint_store=context.store(cp),
            run_root=root,
            resume=False,
        )
    assert calls == [1]
    assert list((tmp_path / "cache").glob("*/CACHE_COMPLETE"))


@pytest.mark.parametrize(
    ("current", "incoming", "limit", "allowed"),
    [(3, 6, 10, True), (3, 7, 10, True), (3, 8, 10, False)],
)
def test_capacity_below_exact_above(current, incoming, limit, allowed):
    assert (capacity_projection(current, incoming) <= limit) is allowed


def test_capacity_rejects_before_temporary_build_preserves_existing(tmp_path, monkeypatch):
    _, fold, prepared, identity = _fixture()
    existing = tmp_path / "protected.bin"
    existing.write_bytes(b"protected evidence")
    monkeypatch.setenv("PHASE7_CACHE_MAX_GB", "0.000000001")
    with pytest.raises(PreparedCacheCapacityError):
        PreparedDataCache(tmp_path, "auto").write(identity, fold, prepared)
    assert existing.read_bytes() == b"protected evidence"
    assert not list(tmp_path.glob(".*.tmp.*"))


def test_descriptor_numerical_change_changes_identity_but_future_does_not():
    records = synthetic_descriptors(as_of=datetime(2022, 1, 1, tzinfo=UTC))
    end = datetime(2022, 1, 1, tzinfo=UTC)
    original = training.causal_descriptor_identity(records, end)
    changed = [records[0].model_copy(update={"realized_volatility": 999.0}), *records[1:]]
    assert training.causal_descriptor_identity(changed, end) != original
    assert training.causal_descriptor_identity(list(reversed(records)), end) == original
    future = records[0].model_copy(update={"as_of": datetime(2023, 1, 1, tzinfo=UTC)})
    assert training.causal_descriptor_identity([*records, future], end) == original


def test_orphan_file_and_report_corruption_rejected_before_deserialization(tmp_path):
    path = tmp_path / "model.joblib"
    path.write_bytes(b"trusted-fixture-estimator")
    report = {"model_artifact_sha256": file_sha256(path), "checkpoint_identity": {"spec": "s"}}
    report["report_identity"] = stable_hash(report, length=64)
    training._validate_model_file_binding(report, path)
    changed = {**report, "checkpoint_identity": {"spec": "different"}}
    with pytest.raises(ValueError, match="content identity"):
        training._validate_model_file_binding(changed, path)
    path.write_bytes(b"swapped-estimator")
    with pytest.raises(ValueError, match="checksum"):
        training._validate_model_file_binding(report, path)
    with pytest.raises(ValueError, match="missing"):
        training._validate_model_file_binding({}, path)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "float32", "inf", "order", "horizon-type", "metadata-type"]
)
def test_full_gold_schema_rejects_self_consistent_corrupted_partition(tmp_path, mutation):
    expectations = _gold_fixture(tmp_path, start=datetime(2025, 1, 1, tzinfo=UTC))
    root = tmp_path / expectations.dataset_id
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    path = root / manifest["partition_files"][0]["path"]
    table = pq.ParquetFile(path).read()
    name = "htf_1d_return"
    if mutation == "missing":
        table = table.drop([name])
    elif mutation == "extra":
        table = table.append_column("htf_1d_unapproved", pa.array([1.0] * table.num_rows))
    elif mutation in {"float32", "horizon-type", "metadata-type"}:
        name, dtype = {
            "float32": (name, pa.float32()),
            "horizon-type": ("horizon_minutes", pa.float64()),
            "metadata-type": ("market_membership_hash", pa.binary()),
        }[mutation]
        table = table.set_column(table.column_names.index(name), name, table[name].cast(dtype))
    elif mutation == "inf":
        table = table.set_column(
            table.column_names.index(name), name, pa.array([float("inf")] * table.num_rows)
        )
    else:
        names = table.column_names
        a, b = names.index("htf_1d_return"), names.index("htf_1d_log_return")
        names[a], names[b] = names[b], names[a]
        table = table.select(names)
    pq.write_table(table, path)
    manifest["partition_files"][0]["sha256"] = file_sha256(path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(GoldValidationError):
        validate_phase7_gold(tmp_path, expectations=expectations)


def test_schema_catalog_and_historical_freeze_remain_independent():
    assert len(production_feature_columns()) == 109
    assert len(production_gold_schema()) == 130
    historical = ROOT / "configs/contracts/phase7_scientific_baseline_v1_9.json"
    assert (
        file_sha256(historical)
        == "a22c17b164792e909f39f619c59ea40db23411c8e611398e11e28d0e98e3f493"
    )
    identity = training.scientific_source_identity()
    assert {
        "src/crypto_ai/phase7/phase7a.py",
        "src/crypto_ai/phase7/benchmark_one_spec.py",
    }.issubset({row["path"] for row in identity["files"]})


def test_one_spec_runner_cannot_complete_production_or_preload_other_keys(tmp_path, monkeypatch):
    cp, _, _ = _patch_harness(monkeypatch, tmp_path, fit_error=ValueError("must not fit"))
    context = _synthetic_registry()
    config = canonical()
    spec = primary_specs(config)[0]
    root = tmp_path / "benchmark-only-test"
    original = context.store(cp)
    store = replace(original, root=root / "checkpoints", run_identity=root.name)
    calls = []

    def run_one(selected, fold, features, config, output, identity, **kwargs):
        calls.append((selected.name, fold.plan.fold_id))
        report = {"status": "COMPLETE", "artifact_mode": "BENCHMARK_ONLY"}
        return report, [atomic_json(output / "report.json", report)]

    monkeypatch.setattr(training, "_run_one", run_one)
    monkeypatch.setattr(
        training,
        "summarize_fold_completion",
        lambda *_: pytest.fail("benchmark entered production completion"),
    )
    result = training.run_phase7_training(
        config,
        gold_manifest_path=tmp_path / "gold/manifest.json",
        registry=context.registry,
        universe=context.universe,
        expansion_policy=context.policy,
        descriptors=context.descriptors,
        checkpoint_store=store,
        run_root=root,
        resume=False,
        benchmark_spec_id=spec.name,
        benchmark_fold_id="fold-000-test",
    )
    assert len(calls) == 1
    assert result["status"] == "BENCHMARK_ONLY"
    assert result["completed_reports"] == result["fold_count"] == 0
    assert result["benchmark_completed_reports"] == 1
    assert not (root / "training_summary.json").exists()


def test_runner_releases_previous_horizon_before_next_spec(tmp_path, monkeypatch):
    cp, root, _ = _patch_harness(monkeypatch, tmp_path, fit_error=ValueError("must not fit"))
    context = _synthetic_registry()
    refs = []
    seen = []
    specs = tuple(
        training.ExperimentSpec(f"G0-{h}", "G0", "A6", h, "raw", symbol_balanced=True)
        for h in (15, 30)
    )
    monkeypatch.setattr(training, "phase7_experiment_specs", lambda _: specs)
    monkeypatch.setattr(training, "slice_multiasset_fold", lambda *_a, **_k: _fold_data(tmp_path))

    def run_one(spec, fold, _features, _config, output, identity, **_kwargs):
        assert all(ref() is None for ref in refs), "previous horizon/view still resident"
        refs.append(weakref.ref(fold.train))
        seen.append((fold.research_view, spec.horizon_minutes))
        report = {
            "status": "INELIGIBLE",
            "spec": asdict(spec),
            "fold_id": fold.plan.fold_id,
            "research_view": fold.research_view,
            "checkpoint_identity": identity,
        }
        return report, [atomic_json(output / "report.json", report)]

    monkeypatch.setattr(training, "_run_one", run_one)
    training.run_phase7_training(
        Phase7Config(),
        gold_manifest_path=tmp_path / "gold/manifest.json",
        registry=context.registry,
        universe=context.universe,
        expansion_policy=context.policy,
        descriptors=context.descriptors,
        checkpoint_store=context.store(cp),
        run_root=root,
        resume=False,
    )
    assert [h for _, h in seen] == [15, 30, 15, 30]
    assert all(ref() is None for ref in refs)


def test_preflight_rejects_old_native_only_gold_pass(tmp_path):
    report = {
        "status": "PASS",
        "partition_hashes_verified": True,
        "dataset_id": "gold",
        "manifest_sha256": "sha",
        "holdout_status": "LOCKED_UNUSED",
    }
    path = atomic_json(tmp_path / "report.json", report)
    with pytest.raises(ValueError, match="incompatible"):
        _validated_gold_report(path, dataset_id="gold", manifest_sha256="sha")
    report["production_features"] = list(production_feature_columns())
    report["production_schema"] = {
        name: str(dtype) for name, dtype in production_gold_schema().items()
    }
    path = atomic_json(tmp_path / "full.json", report)
    assert (
        _validated_gold_report(path, dataset_id="gold", manifest_sha256="sha")["status"] == "PASS"
    )


def test_atomic_publication_fsyncs_file_before_replace_and_directory_after(tmp_path, monkeypatch):
    events = []
    original_replace = artifacts.os.replace
    monkeypatch.setattr(artifacts, "fsync_file", lambda _: events.append("file"))
    monkeypatch.setattr(artifacts, "fsync_directory", lambda _: events.append("directory"))

    def replace(source, target):
        events.append("replace")
        original_replace(source, target)

    monkeypatch.setattr(artifacts.os, "replace", replace)
    atomic_json(tmp_path / "durable.json", {"fixture": True})
    assert events == ["file", "replace", "directory"]


def test_failed_replace_never_publishes_complete_report(tmp_path, monkeypatch):
    def fail(*_args):
        raise OSError("injected publication failure")

    monkeypatch.setattr(artifacts.os, "replace", fail)
    path = tmp_path / "report.json"
    with pytest.raises(OSError, match="injected"):
        atomic_json(path, {"status": "COMPLETE"})
    assert not path.exists()
