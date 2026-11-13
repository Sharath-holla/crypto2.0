"""Pytest plugin: forbid every model fit for a preparation-only session (owner rule 2026-11-13).

Usage:  uv run pytest -p experiments.phase7_low_memory.tools.no_fit_guard ...

Patched before collection: LightGBM sklearn ``fit`` (LGBMModel and subclasses), ``lgb.train``,
``lgb.cv``, ``Booster.refit``/``update``, and scikit-learn linear-model ``fit`` (the Ridge
baselines). Any call raises ``ModelFitForbidden`` BEFORE any boosting/solver work, so a test
that needs a fit fails instead of training. KMeans (TRAIN-only descriptor clustering during
fold preparation) is data preparation, not model training, and is left untouched.
"""

from __future__ import annotations

import pytest


class ModelFitForbidden(RuntimeError):
    pass


def _forbid(name: str):
    def blocked(*_args, **_kwargs):
        raise ModelFitForbidden(f"MODEL_FIT_FORBIDDEN_TODAY: {name}")

    return blocked


def pytest_configure(config: pytest.Config) -> None:
    import lightgbm as lgb
    import sklearn.linear_model as linear

    lgb.LGBMModel.fit = _forbid("LGBMModel.fit")
    for cls in (lgb.LGBMRegressor, lgb.LGBMClassifier, lgb.LGBMRanker):
        cls.fit = _forbid(f"{cls.__name__}.fit")
    lgb.train = _forbid("lightgbm.train")
    lgb.cv = _forbid("lightgbm.cv")
    lgb.engine.train = _forbid("lightgbm.engine.train")
    lgb.sklearn.train = _forbid("lightgbm.sklearn.train")
    lgb.Booster.refit = _forbid("Booster.refit")
    lgb.Booster.update = _forbid("Booster.update")
    for name in (
        "Ridge",
        "RidgeCV",
        "LinearRegression",
        "Lasso",
        "ElasticNet",
        "LogisticRegression",
    ):
        getattr(linear, name).fit = _forbid(f"sklearn.{name}.fit")
    config.addinivalue_line("markers", "no_fit_guard: model fitting is blocked in this session")
