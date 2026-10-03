"""Point-in-time retail forecasting, reproducible data, and explicit model gates."""

from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

KEYS = ["store_id", "sku_id", "date"]
CATEGORICAL = ["store_id", "sku_id", "category", "target_dow"]
FEATURES = CATEGORICAL + [
    "horizon",
    "month",
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "mean_7",
    "mean_28",
    "seasonal_mean",
    "available_fraction_28",
    "origin_available",
    "promo",
    "planned_price",
]


@dataclass(frozen=True)
class Config:
    """Typed experiment configuration; JSON contains no credentials."""

    seed: int
    start_date: str
    days: int
    stores: int
    skus: int
    horizon: int
    origin_stride: int
    n_jobs: int
    n_estimators: int
    tracking_uri: str
    experiment_name: str
    registered_model_name: str
    gates: dict[str, float]


def load_config(path: Path) -> Config:
    """Load and validate JSON, allowing only documented environment overrides."""
    values = json.loads(path.read_text(encoding="utf-8"))
    if "MLFLOW_TRACKING_URI" in os.environ:
        values["tracking_uri"] = os.environ["MLFLOW_TRACKING_URI"]
    if "DDM_SEED" in os.environ:
        values["seed"] = int(os.environ["DDM_SEED"])
    config = Config(**values)
    if config.horizon != 7 or config.origin_stride != 7:
        raise ValueError("Demo protocol fixes a seven-day horizon and disjoint weekly origins")
    if min(config.stores, config.skus, config.n_jobs, config.n_estimators) < 1:
        raise ValueError("Sizes and compute limits must be positive")
    if config.days < 547:
        raise ValueError("The predeclared monthly evaluation needs at least 547 daily observations")
    if not 0 <= config.seed < 2**32:
        raise ValueError("Seed must fit NumPy's random seed range")
    if set(config.gates) != {
        "wape_max",
        "relative_improvement_min",
        "abs_bias_max",
        "group_degradation_pp_max",
    }:
        raise ValueError("Gate keys must match the declared protocol")
    if not all(np.isfinite(value) and value >= 0 for value in config.gates.values()):
        raise ValueError("Gates must be finite and nonnegative")
    if config.gates["relative_improvement_min"] > 100:
        raise ValueError("Relative improvement must not exceed 100 percent")
    return config


def set_seeds(seed: int) -> None:
    """Control Python and NumPy RNGs; estimator seeds are set separately."""
    random.seed(seed)
    np.random.seed(seed)


def file_hash(path: Path) -> str:
    """Hash file contents for immutable artifact lineage."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_data(config: Config) -> pd.DataFrame:
    """Simulate count sales with weekly seasonality, promotion and observed censoring.

    Promotions are published 14 days before their target date. Latent demand is
    retained ONLY for audit, never used as a label or a forecasting feature.
    """
    rng = np.random.default_rng(config.seed)
    dates = pd.date_range(config.start_date, periods=config.days, freq="D")
    records: list[dict[str, Any]] = []
    weekday_factor = np.array([0.88, 0.87, 0.94, 1.00, 1.13, 1.28, 1.12])
    for store in range(config.stores):
        for sku in range(config.skus):
            category = sku % 3
            base = (22 + 5 * (sku % 4)) * (0.90 + 0.10 * store)
            base_price = 12 + 2.5 * sku
            promo = rng.random(config.days) < 0.17
            for day, date in enumerate(dates):
                mu = base * weekday_factor[date.dayofweek]
                mu *= (1 + 0.00022 * day) * (1 + 0.06 * np.sin(2 * np.pi * day / 365.25))
                mu *= 1 + (0.40 + 0.12 * category) * int(promo[day])
                # Gamma-Poisson allows variance above the mean; no Poisson truth claim.
                demand = int(rng.poisson(rng.gamma(80.0, mu / 80.0)))
                available = bool(rng.random() >= 0.04)
                sales = demand if available else int(rng.binomial(demand, 0.45))
                records.append(
                    {
                        "store_id": store,
                        "sku_id": sku,
                        "category": category,
                        "date": date,
                        "sales": sales,
                        "available": int(available),
                        "promo": int(promo[day]),
                        "planned_price": round(base_price * (0.85 if promo[day] else 1), 3),
                        "plan_published_at": date - pd.Timedelta(days=14),
                        "latent_demand_audit_only": demand,
                    }
                )
    return pd.DataFrame(records)


def validate_data(frame: pd.DataFrame) -> None:
    """Reject schema/domain/key errors rather than silently inventing zero sales."""
    required = set(
        KEYS + ["category", "sales", "available", "promo", "planned_price", "plan_published_at"]
    )
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing fields: {required - set(frame.columns)}")
    if frame[list(required)].isna().any().any() or frame.duplicated(KEYS).any():
        raise ValueError("Null required values or duplicate store/SKU/day keys")
    numeric = frame[["sales", "planned_price"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or (numeric < 0).any():
        raise ValueError("Sales and price must be finite and nonnegative")
    if not frame.available.isin([0, 1]).all() or not frame.promo.isin([0, 1]).all():
        raise ValueError("Availability and promotion flags must be binary")
    for _, group in frame.groupby(["store_id", "sku_id"]):
        expected = pd.date_range(group.date.min(), group.date.max(), freq="D")
        if len(group) != len(expected):
            raise ValueError("Missing calendar dates must not be interpreted as zero demand")


def build_features(frame: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Build direct multi-horizon examples using only history through each origin.

    A target's availability is attached for label masking, not exposed in FEATURES.
    At origin o, lag_1 means y(o), lag_7 means y(o-6), consistent with D=o+1.
    """
    records: list[dict[str, Any]] = []
    for (store, sku), group in frame.groupby(["store_id", "sku_id"], sort=True):
        group = group.sort_values("date").reset_index(drop=True)
        observed = group.sales.to_numpy(dtype=float)
        availability = group.available.to_numpy(dtype=bool)
        masked = np.where(availability, observed, np.nan)
        for origin_index in range(55, len(group) - config.horizon, config.origin_stride):
            origin = group.date.iloc[origin_index]
            history = masked[origin_index - 27 : origin_index + 1]
            for horizon in range(1, config.horizon + 1):
                target_index = origin_index + horizon
                target = group.iloc[target_index]
                # Same target weekday over four weeks, all dates <= origin.
                seasonal = [masked[target_index - 7 * k] for k in range(1, 5)]
                if target.plan_published_at > origin:
                    raise ValueError("Future plan was unavailable at the forecast origin")
                records.append(
                    {
                        "store_id": int(store),
                        "sku_id": int(sku),
                        "category": int(target.category),
                        "target_dow": target.date.dayofweek,
                        "origin": origin,
                        "target_date": target.date,
                        "horizon": horizon,
                        "month": target.date.month,
                        "lag_1": masked[origin_index],
                        "lag_7": masked[origin_index - 6],
                        "lag_14": masked[origin_index - 13],
                        "lag_28": masked[origin_index - 27],
                        "mean_7": float(np.nanmean(masked[origin_index - 6 : origin_index + 1])),
                        "mean_28": float(np.nanmean(history)),
                        "seasonal_mean": float(np.nanmean(seasonal))
                        if np.isfinite(seasonal).any()
                        else float(np.nanmean(history)),
                        "available_fraction_28": float(
                            np.mean(availability[origin_index - 27 : origin_index + 1])
                        ),
                        "origin_available": int(availability[origin_index]),
                        "promo": int(target.promo),
                        "planned_price": float(target.planned_price),
                        "target_available": int(target.available),
                        "y": float(target.sales),
                    }
                )
    result = pd.DataFrame(records)
    if not np.isfinite(result[["mean_7", "mean_28", "seasonal_mean"]]).all().all():
        raise ValueError("Insufficient available history: require explicit fallback")
    return result


def temporal_split(
    examples: pd.DataFrame, start: str, end: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Purged expanding split: every training label precedes first evaluation origin."""
    start_date, end_date = pd.Timestamp(start), pd.Timestamp(end)
    candidates = examples[(examples.origin >= start_date) & (examples.target_date <= end_date)]
    # Keep complete seven-horizon origins, including rows masked out later for labels.
    complete = candidates.groupby("origin").horizon.nunique()
    origins = complete[complete == 7].index
    evaluation = candidates[candidates.origin.isin(origins)].copy()
    if evaluation.empty:
        raise ValueError("No complete origins in the declared evaluation window")
    first_origin = evaluation.origin.min()
    # Purge the ENTIRE origin, and do not fit labels from the evaluation month.
    last_labels = examples.groupby("origin").target_date.max()
    training_origins = last_labels[last_labels < min(start_date, first_origin)].index
    training = examples[examples.origin.isin(training_origins)].copy()
    if training.empty or training.target_date.max() >= first_origin:
        raise ValueError("Training label window overlaps evaluation")
    return training, evaluation


class SeasonalBaseline(RegressorMixin, BaseEstimator):
    """Mean-28 or seasonal-four-week baseline with optional train-only promo factor."""

    def __init__(self, feature: str = "seasonal_mean", adjust_promo: bool = False):
        self.feature = feature
        self.adjust_promo = adjust_promo

    def fit(self, x: pd.DataFrame, y: np.ndarray) -> SeasonalBaseline:
        """Estimate a nonnegative promotional multiplier by least squares on train."""
        self.multiplier_ = 1.0
        if self.adjust_promo:
            selected = x.promo.to_numpy() == 1
            base = x[self.feature].to_numpy()[selected]
            actual = np.asarray(y)[selected]
            if len(base) and np.sum(base**2) > 0:
                self.multiplier_ = max(0.0, float(np.sum(base * actual) / np.sum(base**2)))
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """Use only supplied point-in-time features; do not access targets."""
        values = x[self.feature].to_numpy(dtype=float).copy()
        if self.adjust_promo:
            values *= np.where(x.promo.to_numpy() == 1, self.multiplier_, 1.0)
        return values


def experiment_matrix() -> list[dict[str, Any]]:
    """Ten predeclared configurations, with controlled LGBM ablations."""
    return [
        {"id": "E01", "algorithm": "mean28", "features": "full"},
        {"id": "E02", "algorithm": "seasonal", "features": "full"},
        {"id": "E03", "algorithm": "seasonal_promo", "features": "full"},
        {"id": "E04", "algorithm": "ridge", "alpha": 10.0, "features": "full"},
        {
            "id": "E05",
            "algorithm": "lightgbm",
            "objective": "poisson",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "features": "full",
        },
        {
            "id": "E06",
            "algorithm": "lightgbm",
            "objective": "poisson",
            "num_leaves": 15,
            "learning_rate": 0.05,
            "features": "full",
        },
        {
            "id": "E07",
            "algorithm": "lightgbm",
            "objective": "poisson",
            "num_leaves": 63,
            "learning_rate": 0.05,
            "features": "full",
        },
        {
            "id": "E08",
            "algorithm": "lightgbm",
            "objective": "poisson",
            "num_leaves": 31,
            "learning_rate": 0.10,
            "features": "full",
        },
        {
            "id": "E09",
            "algorithm": "lightgbm",
            "objective": "regression_l1",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "features": "full",
        },
        {
            "id": "E10",
            "algorithm": "lightgbm",
            "objective": "poisson",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "features": "no_promo",
        },
    ]


def make_model(spec: dict[str, Any], config: Config) -> tuple[BaseEstimator, list[str]]:
    """Construct train-fitted preprocessing and a single model for seven horizons."""
    features = [
        f
        for f in FEATURES
        if not (spec["features"] == "no_promo" and f in ["promo", "planned_price"])
    ]
    algorithm = spec["algorithm"]
    if algorithm in ["mean28", "seasonal", "seasonal_promo"]:
        return SeasonalBaseline(
            "mean_28" if algorithm == "mean28" else "seasonal_mean", algorithm == "seasonal_promo"
        ), features
    numeric = [f for f in features if f not in CATEGORICAL]
    transforms = [
        ("categories", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
        (
            "numeric",
            Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
            numeric,
        ),
    ]
    preprocess = ColumnTransformer(transforms).set_output(transform="pandas")
    if algorithm == "ridge":
        estimator = Ridge(alpha=spec["alpha"])
    else:
        estimator = LGBMRegressor(
            objective=spec["objective"],
            num_leaves=spec["num_leaves"],
            learning_rate=spec["learning_rate"],
            n_estimators=config.n_estimators,
            min_child_samples=30,
            reg_lambda=1.0,
            random_state=config.seed,
            n_jobs=config.n_jobs,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
        )
    return Pipeline([("preprocess", preprocess), ("model", estimator)]), features


def metrics(y: np.ndarray, predictions: np.ndarray) -> dict[str, float | None]:
    """WAPE and signed bias are percentages; undefined denominators remain null."""
    actual = np.asarray(y, dtype=float)
    predicted = np.asarray(predictions, dtype=float)
    if not len(actual) or len(actual) != len(predicted):
        raise ValueError("Nonempty aligned vectors required")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Nonfinite metric inputs")
    total = float(actual.sum())
    return {
        "wape": float(100 * np.abs(actual - predicted).sum() / total) if total > 0 else None,
        "bias": float(100 * (predicted - actual).sum() / total) if total > 0 else None,
        "mae": float(np.mean(np.abs(actual - predicted))),
        "rmse": float(np.sqrt(np.mean((actual - predicted) ** 2))),
    }


def masked_mase(
    raw: pd.DataFrame, scored: pd.DataFrame, cutoff: pd.Timestamp
) -> dict[str, float | int]:
    """Macro-average per-series MASE; scale from available training pairs only."""
    history = raw[raw.date < cutoff].sort_values(KEYS).copy()
    group = history.groupby(["store_id", "sku_id"])
    history["prev_sales"] = group.sales.shift(7)
    history["prev_available"] = group.available.shift(7)
    usable = history[(history.available == 1) & (history.prev_available == 1)]
    scales = (
        (usable.sales - usable.prev_sales).abs().groupby([usable.store_id, usable.sku_id]).mean()
    )
    errors = (
        scored.assign(error=(scored.y - scored.prediction).abs())
        .groupby(["store_id", "sku_id"])
        .error.mean()
    )
    aligned = pd.concat([errors.rename("error"), scales.rename("scale")], axis=1)
    valid = aligned[aligned.scale.gt(0) & aligned.error.notna()]
    return {
        "mase": float((valid.error / valid.scale).mean()) if len(valid) else float("nan"),
        "mase_valid_series": len(valid),
        "mase_excluded_series": len(errors) - len(valid),
    }


def quality_gate(
    candidate: dict[str, float],
    baseline: dict[str, float],
    worst_group_delta: float,
    gates: dict[str, float],
) -> dict[str, Any]:
    """Evaluate predeclared constraints; never promote based on WAPE alone."""
    if baseline["wape"] <= 0:
        improvement = None
    else:
        improvement = 100 * (baseline["wape"] - candidate["wape"]) / baseline["wape"]
    checks = {
        "wape": np.isfinite(candidate["wape"]) and candidate["wape"] <= gates["wape_max"],
        "improvement": improvement is not None and improvement >= gates["relative_improvement_min"],
        "bias": np.isfinite(candidate["bias"]) and abs(candidate["bias"]) <= gates["abs_bias_max"],
        "groups": np.isfinite(worst_group_delta)
        and worst_group_delta <= gates["group_degradation_pp_max"],
    }
    return {
        "pass": bool(all(checks.values())),
        "checks": {k: bool(v) for k, v in checks.items()},
        "relative_improvement": improvement,
        "worst_group_delta_pp": worst_group_delta,
    }
