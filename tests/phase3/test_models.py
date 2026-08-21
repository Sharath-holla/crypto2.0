from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from crypto_ai.research.config import (
    BASELINE_FEATURE_COLUMNS,
    ExperimentConfig,
    LightGBMConfig,
)
from crypto_ai.research.models import load_model, save_model, train_model


def _arrays(seed: int = 7):
    generator = np.random.default_rng(seed)
    train_x = generator.normal(size=(160, len(BASELINE_FEATURE_COLUMNS)))
    validation_x = generator.normal(size=(60, len(BASELINE_FEATURE_COLUMNS)))
    coefficients = np.linspace(-0.0004, 0.0006, len(BASELINE_FEATURE_COLUMNS))
    train_y = train_x @ coefficients + generator.normal(scale=0.0001, size=160)
    validation_y = validation_x @ coefficients + generator.normal(scale=0.0001, size=60)
    return train_x, train_y, validation_x, validation_y


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("zero", lambda train_y, validation_x: np.zeros(len(validation_x))),
        (
            "historical_mean",
            lambda train_y, validation_x: np.full(len(validation_x), np.mean(train_y)),
        ),
        (
            "momentum",
            lambda train_y, validation_x: validation_x[
                :, BASELINE_FEATURE_COLUMNS.index("return_1h")
            ],
        ),
        (
            "mean_reversion",
            lambda train_y, validation_x: (
                -validation_x[:, BASELINE_FEATURE_COLUMNS.index("ema20_distance")]
            ),
        ),
    ],
)
def test_deterministic_baselines(model_name, expected) -> None:
    train_x, train_y, validation_x, validation_y = _arrays()
    trained = train_model(
        model_name,
        train_x,
        train_y,
        validation_x,
        validation_y,
        feature_columns=BASELINE_FEATURE_COLUMNS,
        config=ExperimentConfig(models=(model_name,)),
        common_metadata={},
    )

    actual = trained.bundle.predict(validation_x, BASELINE_FEATURE_COLUMNS)
    np.testing.assert_allclose(actual, expected(train_y, validation_x))


def test_ridge_scaler_is_fit_on_training_data_only() -> None:
    train_x, train_y, validation_x, validation_y = _arrays()
    validation_x += 100.0
    trained = train_model(
        "ridge",
        train_x,
        train_y,
        validation_x,
        validation_y,
        feature_columns=BASELINE_FEATURE_COLUMNS,
        config=ExperimentConfig(models=("ridge",)),
        common_metadata={},
    )

    scaler_mean = np.asarray(trained.bundle.metadata["training_only_scaler_mean"])
    np.testing.assert_allclose(scaler_mean, np.mean(train_x, axis=0))
    assert not np.allclose(scaler_mean, np.mean(np.vstack([train_x, validation_x]), axis=0))
    assert np.all(np.isfinite(trained.bundle.predict(validation_x, BASELINE_FEATURE_COLUMNS)))


def test_model_artifact_reload_reproduces_predictions_and_enforces_schema(
    tmp_path: Path,
) -> None:
    train_x, train_y, validation_x, validation_y = _arrays()
    trained = train_model(
        "ridge",
        train_x,
        train_y,
        validation_x,
        validation_y,
        feature_columns=BASELINE_FEATURE_COLUMNS,
        config=ExperimentConfig(models=("ridge",)),
        common_metadata={"dataset_version": "gold-test"},
    )
    path = tmp_path / "ridge.joblib"
    save_model(trained.bundle, path)
    reloaded = load_model(path)

    np.testing.assert_allclose(
        reloaded.predict(validation_x, BASELINE_FEATURE_COLUMNS),
        trained.bundle.predict(validation_x, BASELINE_FEATURE_COLUMNS),
    )
    with pytest.raises(ValueError, match="missing"):
        reloaded.predict(validation_x[:, :-1], BASELINE_FEATURE_COLUMNS[:-1])
    with pytest.raises(ValueError, match="extra"):
        reloaded.predict(
            np.column_stack([validation_x, np.zeros(len(validation_x))]),
            (*BASELINE_FEATURE_COLUMNS, "unexpected"),
        )
    with pytest.raises(ValueError, match="NaN"):
        invalid = validation_x.copy()
        invalid[0, 0] = np.nan
        reloaded.predict(invalid, BASELINE_FEATURE_COLUMNS)


def test_lightgbm_trains_predicts_and_reports_importance(tmp_path: Path) -> None:
    train_x, train_y, validation_x, validation_y = _arrays()
    config = ExperimentConfig(
        models=("lightgbm",),
        lightgbm=LightGBMConfig(
            n_estimators=80,
            learning_rate=0.05,
            num_leaves=7,
            max_depth=3,
            min_child_samples=5,
            early_stopping_rounds=10,
        ),
    )
    trained = train_model(
        "lightgbm",
        train_x,
        train_y,
        validation_x,
        validation_y,
        feature_columns=BASELINE_FEATURE_COLUMNS,
        config=config,
        common_metadata={},
    )
    predictions = trained.bundle.predict(validation_x, BASELINE_FEATURE_COLUMNS)

    assert predictions.shape == validation_y.shape
    assert np.all(np.isfinite(predictions))
    assert trained.bundle.metadata["best_iteration"] > 0
    assert set(trained.feature_importance["gain"]) == set(BASELINE_FEATURE_COLUMNS)
    assert set(trained.feature_importance["validation_permutation_mae"]) == set(
        BASELINE_FEATURE_COLUMNS
    )
    for summary in trained.feature_importance["validation_permutation_mae"].values():
        assert set(summary) == {"mean", "std"}
    path = tmp_path / "lightgbm.joblib"
    save_model(trained.bundle, path)
    np.testing.assert_allclose(
        load_model(path).predict(validation_x, BASELINE_FEATURE_COLUMNS), predictions
    )


def test_shuffled_training_labels_collapse_a_known_synthetic_signal() -> None:
    generator = np.random.default_rng(42)
    train_x = generator.normal(size=(500, len(BASELINE_FEATURE_COLUMNS)))
    validation_x = generator.normal(size=(200, len(BASELINE_FEATURE_COLUMNS)))
    train_y = 0.8 * train_x[:, 0] - 0.3 * train_x[:, 1]
    validation_y = 0.8 * validation_x[:, 0] - 0.3 * validation_x[:, 1]
    config = ExperimentConfig(models=("ridge",))
    fitted = train_model(
        "ridge",
        train_x,
        train_y,
        validation_x,
        validation_y,
        feature_columns=BASELINE_FEATURE_COLUMNS,
        config=config,
        common_metadata={},
    )
    shuffled = train_model(
        "ridge",
        train_x,
        generator.permutation(train_y),
        validation_x,
        validation_y,
        feature_columns=BASELINE_FEATURE_COLUMNS,
        config=config,
        common_metadata={},
    )

    fitted_correlation = np.corrcoef(
        fitted.bundle.predict(validation_x, BASELINE_FEATURE_COLUMNS), validation_y
    )[0, 1]
    shuffled_correlation = np.corrcoef(
        shuffled.bundle.predict(validation_x, BASELINE_FEATURE_COLUMNS), validation_y
    )[0, 1]
    assert fitted_correlation > 0.99
    assert abs(shuffled_correlation) < 0.25
