from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_ai.cli import main
from tests.research_helpers import make_research_candles, write_silver_dataset


def _last_json(output: str) -> dict:
    return json.loads(output.strip().splitlines()[-1])


def _experiment_config(path: Path) -> None:
    path.write_text(
        """
[experiment]
models = ["zero", "historical_mean", "momentum", "mean_reversion", "ridge", "lightgbm"]
seed = 42
artifact_root = "unused"

[split]
train_fraction = 0.70
validation_fraction = 0.15
test_fraction = 0.15
minimum_rows_per_split = 10

[ridge]
alpha = 1.0

[lightgbm]
n_estimators = 80
learning_rate = 0.05
num_leaves = 7
max_depth = 3
min_child_samples = 5
subsample = 0.8
colsample_bytree = 0.8
reg_alpha = 0.1
reg_lambda = 1.0
early_stopping_rounds = 10
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_build_train_and_evaluate_cli_pipeline(tmp_path: Path, capsys) -> None:
    silver_manifest, _ = write_silver_dataset(tmp_path, make_research_candles(450))
    gold_root = tmp_path / "gold"
    artifact_root = tmp_path / "artifacts"
    config_path = tmp_path / "experiment.toml"
    _experiment_config(config_path)

    assert (
        main(
            [
                "build-dataset",
                "--silver-manifest",
                str(silver_manifest),
                "--output-root",
                str(gold_root),
            ]
        )
        == 0
    )
    build = _last_json(capsys.readouterr().out)
    gold_manifest = Path(build["manifest"])
    assert build["row_count"] == 388
    assert build["feature_count"] == 13
    assert not build["reused"]

    assert (
        main(
            [
                "train",
                "--dataset-manifest",
                str(gold_manifest),
                "--config",
                str(config_path),
                "--artifact-root",
                str(artifact_root),
            ]
        )
        == 0
    )
    train_output = capsys.readouterr().out
    trained = _last_json(train_output)
    experiment_path = Path(trained["experiment"])
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    assert "Model | MAE | RMSE" in train_output
    assert "Spearman" in train_output
    assert trained["status"] == "complete"
    assert set(trained["models"]) == {
        "zero",
        "historical_mean",
        "momentum",
        "mean_reversion",
        "ridge",
        "lightgbm",
    }
    assert experiment["split"]["purged_train_rows"] == 12
    assert experiment["split"]["purged_validation_rows"] == 12
    assert (
        experiment["split"]["validation_start"] == experiment["split"]["validation_period"]["start"]
    )
    assert experiment["split"]["test_start"] == experiment["split"]["test_period"]["start"]
    assert len(experiment["comparison"]) == 6

    for model_name, artifacts in experiment["models"].items():
        assert (experiment_path.parent / artifacts["model"]).exists()
        prediction_path = experiment_path.parent / artifacts["predictions"]
        predictions = pq.ParquetFile(prediction_path).read()
        assert predictions.num_rows == (
            experiment["split"]["validation_rows"] + experiment["split"]["test_rows"]
        )
        assert set(predictions.column("split").to_pylist()) == {"validation", "test"}
        assert set(predictions.column("model_name").to_pylist()) == {model_name}

    assert main(["evaluate", "--experiment", str(experiment_path)]) == 0
    evaluation_output = capsys.readouterr().out
    evaluation = _last_json(evaluation_output)
    assert evaluation["experiment_id"] == trained["experiment_id"]
    assert evaluation["status"] == "complete"


def test_build_dataset_cli_rerun_is_idempotent(tmp_path: Path, capsys) -> None:
    silver_manifest, _ = write_silver_dataset(tmp_path, make_research_candles(100))
    arguments = [
        "build-dataset",
        "--silver-manifest",
        str(silver_manifest),
        "--output-root",
        str(tmp_path / "gold"),
    ]

    assert main(arguments) == 0
    first = _last_json(capsys.readouterr().out)
    assert main(arguments) == 0
    second = _last_json(capsys.readouterr().out)

    assert not first["reused"]
    assert second["reused"]
    assert first["dataset_version"] == second["dataset_version"]
    assert first["dataset"] == second["dataset"]


def test_invalid_feature_config_has_clear_cli_error(tmp_path: Path) -> None:
    silver_manifest, _ = write_silver_dataset(tmp_path, make_research_candles(100))
    config_path = tmp_path / "invalid-features.toml"
    config_path.write_text(
        '[features]\nversion = "bad"\ncolumns = ["future_return_60m"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="leakage-reviewed"):
        main(
            [
                "build-dataset",
                "--silver-manifest",
                str(silver_manifest),
                "--feature-config",
                str(config_path),
                "--output-root",
                str(tmp_path / "gold"),
            ]
        )
