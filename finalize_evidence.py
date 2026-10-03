"""Verify the logged model roundtrip and attach explicit post-format lineage evidence."""

import json
import os
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("UV_CACHE_DIR", str(Path(".uv-cache").resolve()))

import src  # noqa: F401 -- initializes app-local native DLL search before model loading
import joblib
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
import numpy as np
import pandas as pd

from run_experiments import environment_manifest
from src.forecasting import file_hash, load_config

root = Path(__file__).resolve().parent
out = root / "artifacts"
config = load_config(root / "configs/demo.json")
environment_manifest(out)
environment = json.loads((out / "environment.json").read_text(encoding="utf-8"))
mlflow.set_tracking_uri(config.tracking_uri)
registry = json.loads((out / "registry.json").read_text(encoding="utf-8"))
client = MlflowClient()
features = json.loads((out / "selected_features.json").read_text(encoding="utf-8"))
examples = pd.read_parquet(out / "examples.parquet")[features].head(100)
local = joblib.load(out / "selected_model.joblib")
(out / "roundtrip").mkdir(exist_ok=True)
logged = mlflow.sklearn.load_model(registry["model_uri"], dst_path=str(out / "roundtrip"))
delta = float(np.max(np.abs(logged.predict(examples) - local.predict(examples))))
if delta > 1e-10:
    raise ValueError(f"Registry roundtrip changed predictions: {delta}")
run_ids = list(pd.read_csv(out / "fold_results.csv").run_id) + [registry["run_id"]]
for run_id in run_ids:
    client.set_tag(run_id, "source_sha256_post_format", file_hash(root / "run_experiments.py"))
    client.set_tag(run_id, "config_sha256", file_hash(root / "configs/demo.json"))
    client.set_tag(
        run_id, "lineage_note", "Source formatted after execution; numerical logic unchanged"
    )
    client.log_dict(run_id, environment, "environment_finalized.json")
summary = {
    "model_roundtrip_max_abs_difference": delta,
    "successful_current_run_count": len(run_ids),
    "all_current_runs_finished": all(client.get_run(i).info.status == "FINISHED" for i in run_ids),
    "source_formatted_after_execution": True,
}
(out / "roundtrip_verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary))
