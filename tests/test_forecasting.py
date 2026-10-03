"""Contract and leakage tests protecting scientific claims, not implementation trivia."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.forecasting import (
    FEATURES,
    build_features,
    generate_data,
    load_config,
    metrics,
    quality_gate,
    temporal_split,
    validate_data,
)


@pytest.fixture
def demo_data():
    config = replace(load_config(Path("configs/demo.json")), stores=1, skus=2)
    raw = generate_data(config)
    return config, raw, build_features(raw, config)


def test_future_sales_cannot_change_origin_features(demo_data):
    config, raw, examples = demo_data
    origin = examples.origin.iloc[20]
    altered = raw.copy()
    altered.loc[altered.date > origin, "sales"] = 99999
    rebuilt = build_features(altered, config)
    pd.testing.assert_frame_equal(
        examples[examples.origin == origin][FEATURES].reset_index(drop=True),
        rebuilt[rebuilt.origin == origin][FEATURES].reset_index(drop=True),
    )


def test_censored_target_not_exposed_as_feature(demo_data):
    assert "target_available" not in FEATURES
    assert "y" not in FEATURES
    assert not any("latent" in feature for feature in FEATURES)


def test_purged_split_keeps_future_labels_out(demo_data):
    _, _, examples = demo_data
    training, evaluation = temporal_split(examples, "2025-01-01", "2025-01-31")
    assert training.target_date.max() < evaluation.origin.min()
    assert training.target_date.max() < pd.Timestamp("2025-01-01")
    assert training.groupby("origin").horizon.nunique().eq(7).all()
    assert not set(training.origin).intersection(evaluation.origin)


def test_unpublished_plan_rejected(demo_data):
    config, raw, _ = demo_data
    raw["plan_published_at"] = raw.date + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="unavailable"):
        build_features(raw, config)


def test_duplicate_keys_rejected(demo_data):
    _, raw, _ = demo_data
    with pytest.raises(ValueError, match="duplicate"):
        validate_data(pd.concat([raw, raw.iloc[:1]]))


def test_missing_day_is_not_zero_imputed(demo_data):
    _, raw, _ = demo_data
    with pytest.raises(ValueError, match="Missing calendar"):
        validate_data(raw.drop(raw.index[50]))


def test_zero_denominator_metrics_remain_undefined():
    result = metrics(np.zeros(3), np.ones(3))
    assert result["wape"] is None and result["bias"] is None
    assert result["mae"] == 1.0


def test_better_wape_cannot_bypass_bias_or_group_gate():
    gates = load_config(Path("configs/demo.json")).gates
    baseline = {"wape": 30.0, "bias": 0.0}
    assert not quality_gate({"wape": 20.0, "bias": 6.0}, baseline, 0, gates)["pass"]
    assert not quality_gate({"wape": 20.0, "bias": 0.0}, baseline, 3.0, gates)["pass"]
    assert quality_gate({"wape": 20.0, "bias": 0.0}, baseline, 0, gates)["pass"]
