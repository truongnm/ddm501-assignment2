"""Run ten predeclared experiments and evaluate one locked final configuration.

Usage: python run_experiments.py --config configs/demo.json --out artifacts
All outputs are synthetic coursework evidence, never production approval.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).parent / "artifacts" / "matplotlib"))
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
import numpy as np
import pandas as pd

from src.forecasting import (
    Config,
    build_features,
    experiment_matrix,
    file_hash,
    generate_data,
    load_config,
    make_model,
    masked_mase,
    metrics,
    quality_gate,
    set_seeds,
    temporal_split,
    validate_data,
)

WINDOWS = [("2025-01-01", "2025-01-31"), ("2025-02-01", "2025-02-28"), ("2025-03-01", "2025-03-31")]


def write_json(path: Path, value: Any) -> None:
    """Atomically publish a local JSON artifact, preventing truncated readers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def prepare(config: Config, out: Path) -> None:
    """Generate, validate and freeze raw and feature artifacts for the demo."""
    out.mkdir(parents=True, exist_ok=True)
    raw = generate_data(config)
    validate_data(raw)
    raw.to_parquet(out / "synthetic_sales.parquet", index=False)
    examples = build_features(raw, config)
    examples.to_parquet(out / "examples.parquet", index=False)
    write_json(
        out / "data_manifest.json",
        {
            "evidence_type": "synthetic",
            "generator": "gamma_poisson_retail_v1",
            "seed": config.seed,
            "raw_rows": len(raw),
            "example_rows": len(examples),
            "series": config.stores * config.skus,
            "date_min": str(raw.date.min().date()),
            "date_max": str(raw.date.max().date()),
            "raw_sha256": file_hash(out / "synthetic_sales.parquet"),
            "feature_sha256": file_hash(out / "examples.parquet"),
            "availability_fraction": float(raw.available.mean()),
            "latent_demand_used_for_training": False,
        },
    )


def group_delta(candidate: pd.DataFrame, baseline: pd.DataFrame) -> float:
    """Worst WAPE difference for predeclared store/category slices on identical rows."""
    differences: list[float] = []
    for field in ["store_id", "category"]:
        for value, group in candidate.groupby(field):
            control = baseline[baseline[field] == value]
            if len(group) >= 100 and group.y.sum() >= candidate.y.sum() * 0.01:
                differences.append(
                    float(
                        metrics(group.y, group.prediction)["wape"]
                        - metrics(control.y, control.prediction)["wape"]
                    )
                )
    return max(differences) if differences else float("inf")


def benchmark(model: Any, x: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Warm up then time seven repeat batch calls; return the nearest-rank p95."""
    model.predict(x.iloc[: min(100, len(x))])
    elapsed = []
    predictions = np.array([])
    for _ in range(7):
        started = time.perf_counter()
        predictions = np.maximum(0.0, model.predict(x))
        elapsed.append(1000 * (time.perf_counter() - started))
    # Seven observations are only a microbenchmark, not a production SLO estimate.
    return predictions, float(np.quantile(elapsed, 0.95, method="higher"))


def search(config: Config, out: Path) -> None:
    """Fit each configuration on three purged expanding folds, logging actual runs."""
    raw = pd.read_parquet(out / "synthetic_sales.parquet")
    examples = pd.read_parquet(out / "examples.parquet")
    manifest = json.loads((out / "data_manifest.json").read_text(encoding="utf-8"))
    mlflow.set_tracking_uri(config.tracking_uri)
    mlflow.set_experiment(config.experiment_name)
    write_json(out / "experiment_matrix.json", experiment_matrix())
    rows = []
    all_predictions = []
    for spec in experiment_matrix():
        for fold, (start, end) in enumerate(WINDOWS, 1):
            training, evaluation = temporal_split(examples, start, end)
            train = training[training.target_available == 1]
            valid = evaluation[evaluation.target_available == 1].copy()
            model, features = make_model(spec, config)
            with mlflow.start_run(run_name=f"{spec['id']}-fold{fold}") as run:
                mlflow.set_tags(
                    {
                        "evidence_type": "synthetic",
                        "phase": "validation",
                        "data_sha256": manifest["raw_sha256"],
                    }
                )
                mlflow.log_params(
                    {
                        **spec,
                        "seed": config.seed,
                        "n_jobs": config.n_jobs,
                        "n_estimators": config.n_estimators,
                        "fold": fold,
                        "validation_start": start,
                        "validation_end": end,
                        "label_max_train": str(train.target_date.max().date()),
                        "origin_min_validation": str(valid.origin.min().date()),
                    }
                )
                started = time.perf_counter()
                model.fit(train[features], train.y.to_numpy())
                fit_seconds = time.perf_counter() - started
                predictions, latency = benchmark(model, valid[features])
                valid["prediction"] = predictions
                valid["experiment"] = spec["id"]
                valid["fold"] = fold
                score = metrics(valid.y.to_numpy(), predictions)
                score.update(
                    masked_mase(raw, valid, train.target_date.max() + pd.Timedelta(days=1))
                )
                score.update(
                    {
                        "fit_seconds": fit_seconds,
                        "batch_p95_ms": latency,
                        "coverage": len(valid) / len(evaluation),
                    }
                )
                mlflow.log_metrics({k: float(v) for k, v in score.items() if v is not None})
                mlflow.log_dict({"features": features, "spec": spec}, "feature_config.json")
                rows.append(
                    {
                        "id": spec["id"],
                        "fold": fold,
                        **score,
                        "n_train": len(train),
                        "n_evaluation": len(valid),
                        "run_id": run.info.run_id,
                    }
                )
                all_predictions.append(valid)
                print(f"{spec['id']} fold {fold}: WAPE={score['wape']:.3f}%", flush=True)
    fold_results = pd.DataFrame(rows)
    fold_results.to_csv(out / "fold_results.csv", index=False)
    predictions = pd.concat(all_predictions, ignore_index=True)
    predictions.to_parquet(out / "validation_predictions.parquet", index=False)
    summaries = []
    for spec in experiment_matrix():
        folds = fold_results[fold_results.id == spec["id"]]
        pooled = predictions[predictions.experiment == spec["id"]]
        score = metrics(pooled.y, pooled.prediction)
        summaries.append(
            {
                "id": spec["id"],
                **spec,
                **score,
                "wape_cv_mean": float(folds.wape.mean()),
                "wape_cv_sd": float(folds.wape.std(ddof=1)),
                "mase_mean": float(folds.mase.mean()),
                "fit_seconds_mean": float(folds.fit_seconds.mean()),
                "batch_p95_ms_mean": float(folds.batch_p95_ms.mean()),
                "coverage": float(folds.coverage.mean()),
            }
        )
    summary = pd.DataFrame(summaries)
    baseline_id = summary[summary.id.isin(["E01", "E02", "E03"])].sort_values("wape").iloc[0].id
    base_predictions = predictions[predictions.experiment == baseline_id]
    baseline_score = metrics(base_predictions.y, base_predictions.prediction)
    gates: dict[str, Any] = {}
    for spec in experiment_matrix():
        scored = predictions[predictions.experiment == spec["id"]]
        gates[spec["id"]] = quality_gate(
            metrics(scored.y, scored.prediction),
            baseline_score,
            group_delta(scored, base_predictions),
            config.gates,
        )
    summary["gate_pass"] = summary.id.map(lambda value: gates[value]["pass"])
    summary.to_csv(out / "experiment_results.csv", index=False)
    candidates = summary[summary.gate_pass & ~summary.id.isin(["E01", "E02", "E03"])]
    status = "validation_pass" if len(candidates) else "validation_rejected_keep_baseline"
    if candidates.empty:
        candidates = summary[~summary.id.isin(["E01", "E02", "E03"])]
    chosen = candidates.sort_values(["wape", "fit_seconds_mean"]).iloc[0].id
    write_json(
        out / "selection.json",
        {
            "selected_id": chosen,
            "baseline_id": baseline_id,
            "status": status,
            "selected_spec": next(s for s in experiment_matrix() if s["id"] == chosen),
            "baseline_spec": next(s for s in experiment_matrix() if s["id"] == baseline_id),
            "gates": gates,
            "test_used_for_selection": False,
            "tie_break": "minimum pooled validation WAPE, then fit time; no significance claim",
        },
    )


def bootstrap_difference(scored: pd.DataFrame, baseline: pd.DataFrame, seed: int) -> dict[str, Any]:
    """Paired origin-week block bootstrap; conditional illustration with few blocks."""
    keys = ["store_id", "sku_id", "origin", "horizon"]
    pair = scored[keys + ["y", "prediction"]].merge(
        baseline[keys + ["prediction"]], on=keys, suffixes=("", "_base"), validate="one_to_one"
    )
    pair["abs_model"] = (pair.y - pair.prediction).abs()
    pair["abs_base"] = (pair.y - pair.prediction_base).abs()
    blocks = pair.groupby("origin")[["y", "abs_model", "abs_base"]].sum().to_numpy()
    rng = np.random.default_rng(seed)
    draws = blocks[rng.integers(0, len(blocks), size=(2000, len(blocks)))].sum(axis=1)
    differences = 100 * (draws[:, 1] - draws[:, 2]) / draws[:, 0]
    return {
        "difference_wape_pp_95ci": np.quantile(differences, [0.025, 0.975]).tolist(),
        "blocks": len(blocks),
        "replicates": 2000,
        "scope": "conditional on synthetic series; not business causal evidence",
    }


def evaluate_locked(config: Config, out: Path) -> None:
    """Lock selection first, refit, evaluate final test once, and save candidate model."""
    selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    raw = pd.read_parquet(out / "synthetic_sales.parquet")
    examples = pd.read_parquet(out / "examples.parquet")
    training, evaluation = temporal_split(examples, "2025-04-01", "2025-06-30")
    train = training[training.target_available == 1]
    valid = evaluation[evaluation.target_available == 1].copy()
    specs = [selection["selected_spec"], selection["baseline_spec"]]
    models: dict[str, Any] = {}
    test_scores: dict[str, Any] = {}
    predictions: dict[str, pd.DataFrame] = {}
    for spec in specs:
        model, features = make_model(spec, config)
        started = time.perf_counter()
        model.fit(train[features], train.y.to_numpy())
        fit_seconds = time.perf_counter() - started
        predicted, latency = benchmark(model, valid[features])
        scored = valid.copy()
        scored["prediction"] = predicted
        score = metrics(scored.y, predicted)
        score.update(masked_mase(raw, scored, train.target_date.max() + pd.Timedelta(days=1)))
        score.update(
            {
                "fit_seconds": fit_seconds,
                "batch_p95_ms": latency,
                "n_test": len(scored),
                "coverage": len(scored) / len(evaluation),
            }
        )
        test_scores[spec["id"]] = score
        predictions[spec["id"]] = scored
        models[spec["id"]] = model
        scored.to_parquet(out / f"test_predictions_{spec['id']}.parquet", index=False)
    selected_id, baseline_id = selection["selected_id"], selection["baseline_id"]
    gate = quality_gate(
        test_scores[selected_id],
        test_scores[baseline_id],
        group_delta(predictions[selected_id], predictions[baseline_id]),
        config.gates,
    )
    result = {
        "evidence_type": "synthetic",
        "selected_id": selected_id,
        "baseline_id": baseline_id,
        "scores": test_scores,
        "test_gate": gate,
        "train_label_max": str(train.target_date.max().date()),
        "test_origin_min": str(evaluation.origin.min().date()),
        "test_origin_max": str(evaluation.origin.max().date()),
        "eligible_test_rows": len(valid),
        "all_test_rows": len(evaluation),
        "uncertainty": bootstrap_difference(
            predictions[selected_id], predictions[baseline_id], config.seed
        ),
        "production_release_authorized": False,
    }
    write_json(out / "test_results.json", result)
    joblib.dump(models[selected_id], out / "selected_model.joblib")
    _, features = make_model(selection["selected_spec"], config)
    write_json(out / "selected_features.json", features)
    slice_rows = []
    for identifier, scored in predictions.items():
        for field in ["horizon", "store_id", "category"]:
            for value, group in scored.groupby(field):
                slice_rows.append(
                    {
                        "id": identifier,
                        "slice": field,
                        "value": int(value),
                        "n": len(group),
                        **metrics(group.y, group.prediction),
                    }
                )
    pd.DataFrame(slice_rows).to_csv(out / "test_slices.csv", index=False)
    draw_figures(out)


def register_demo(config: Config, out: Path) -> None:
    """Log model/signature/artifacts and register a DEMO candidate, never champion."""
    selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    result = json.loads((out / "test_results.json").read_text(encoding="utf-8"))
    features = json.loads((out / "selected_features.json").read_text(encoding="utf-8"))
    model = joblib.load(out / "selected_model.joblib")
    example = pd.read_parquet(out / "examples.parquet")[features].head(5)
    mlflow.set_tracking_uri(config.tracking_uri)
    mlflow.set_experiment(config.experiment_name)
    with mlflow.start_run(run_name="locked-test-demo-candidate") as run:
        mlflow.set_tags(
            {
                "evidence_type": "synthetic",
                "phase": "locked_test",
                "deployment_allowed": "false",
                "selection_id": selection["selected_id"],
            }
        )
        mlflow.log_params(
            {
                **selection["selected_spec"],
                "seed": config.seed,
                "selection_sha256": file_hash(out / "selection.json"),
            }
        )
        mlflow.log_metrics(
            {
                k: float(v)
                for k, v in result["scores"][selection["selected_id"]].items()
                if isinstance(v, (float, int))
            }
        )
        for filename in [
            "data_manifest.json",
            "selection.json",
            "test_results.json",
            "experiment_matrix.json",
            "experiment_results.csv",
            "test_slices.csv",
        ]:
            mlflow.log_artifact(str(out / filename))
        mlflow.log_dict(asdict(config), "config.json")
        signature = infer_signature(example, np.maximum(0.0, model.predict(example)))
        # The saved regressor emits raw output; serving MUST enforce the documented nonnegative clip.
        info = mlflow.sklearn.log_model(
            model,
            name="model",
            signature=signature,
            input_example=example,
            skops_trusted_types=[
                "collections.OrderedDict",
                "lightgbm.basic.Booster",
                "lightgbm.sklearn.LGBMRegressor",
                "numpy.dtype",
            ],
            registered_model_name=config.registered_model_name,
        )
        version = str(info.registered_model_version)
        client = MlflowClient()
        client.set_model_version_tag(
            config.registered_model_name, version, "evidence_type", "synthetic"
        )
        client.set_model_version_tag(
            config.registered_model_name, version, "deployment_allowed", "false"
        )
        client.set_registered_model_alias(config.registered_model_name, "demo_candidate", version)
        write_json(
            out / "registry.json",
            {
                "model_name": config.registered_model_name,
                "version": version,
                "alias": "demo_candidate",
                "model_uri": info.model_uri,
                "run_id": run.info.run_id,
                "production_promoted": False,
            },
        )


def draw_figures(out: Path) -> None:
    """Generate static exportable research figures from measured artifacts."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    data = pd.read_csv(out / "experiment_results.csv")
    fig, ax = plt.subplots(figsize=(9, 4.2), layout="constrained")
    ax.bar(
        data.id,
        data.wape_cv_mean,
        yerr=data.wape_cv_sd,
        capsize=3,
        color=["#7b8794" if i in ["E01", "E02", "E03"] else "#167a86" for i in data.id],
    )
    ax.axhline(25, color="#a33d46", linestyle="--", label="Proposed WAPE gate: 25%")
    ax.set(
        ylabel="Validation WAPE (%)",
        xlabel="Predeclared experiment",
        title="Synthetic retail: 3 temporal folds (mean ± sample SD)",
    )
    ax.legend(fontsize=9)
    fig.savefig(out / "validation_comparison.png", dpi=180)
    plt.close(fig)
    slices = pd.read_csv(out / "test_slices.csv")
    fig, ax = plt.subplots(figsize=(9, 3.6), layout="constrained")
    for identifier, group in slices[slices.slice == "horizon"].groupby("id"):
        ax.plot(group.value, group.wape, marker="o", label=identifier)
    ax.set(
        xlabel="Forecast horizon (days)",
        ylabel="Locked-test WAPE (%)",
        title="Selected configuration and locked baseline only",
    )
    ax.legend()
    fig.savefig(out / "test_horizons.png", dpi=180)
    plt.close(fig)


def environment_manifest(out: Path) -> None:
    """Record packages, platform, configuration and source hashes; tolerate no Git repo."""
    packages = subprocess.check_output(
        [
            os.sys.executable,
            "-c",
            "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name']: d.version for d in m.distributions()}))",
        ],
        text=True,
    )
    root = Path(__file__).parent
    sources = [
        root / "run_experiments.py",
        root / "src" / "forecasting.py",
        root / "configs" / "demo.json",
    ]
    write_json(
        out / "environment.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "packages": json.loads(packages),
            "source_sha256": {str(p.relative_to(root)): file_hash(p) for p in sources},
            "git_sha": None,
            "git_note": "Source hashes recorded; no Git release asserted",
            "docker_executed": False,
            "airflow_executed": False,
        },
    )


def main() -> None:
    """CLI supports individually orchestrated artifact-producing stages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/demo.json"))
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--stage", choices=["prepare", "search", "evaluate", "register", "all"], default="all"
    )
    args = parser.parse_args()
    config = load_config(args.config)
    set_seeds(config.seed)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.stage in ["prepare", "all"]:
        prepare(config, out)
    if args.stage in ["search", "all"]:
        search(config, out)
    if args.stage in ["evaluate", "all"]:
        evaluate_locked(config, out)
    if args.stage in ["register", "all"]:
        register_demo(config, out)
    environment_manifest(out)
    print(f"Completed stage {args.stage}; artifacts: {out}", flush=True)


if __name__ == "__main__":
    main()
