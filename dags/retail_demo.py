"""Airflow 3 design example; install on Linux with a shared artifact volume.

No external calls, training, or data reads occur when the scheduler parses this file.
This DAG creates educational artifacts, not ERP orders or a production release.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from airflow.sdk import dag, get_current_context, task


def failure_alert(context: dict[str, Any]) -> None:
    """Emit structured failure logs; production routes them to the on-call receiver."""
    logging.error(
        "Pipeline failure task=%s run=%s exception=%s",
        context.get("task_instance"),
        context.get("run_id"),
        context.get("exception"),
    )


def run_stage(stage: str, output_path: str) -> str:
    """Call versioned CLI in isolated process; return only a small artifact reference."""
    project_root = Path(os.environ.get("DDM_PROJECT_ROOT", "/app")).resolve()
    subprocess.run(
        [
            sys.executable,
            str(project_root / "run_experiments.py"),
            "--config",
            str(project_root / "configs" / "demo.json"),
            "--out",
            output_path,
            "--stage",
            stage,
        ],
        cwd=project_root,
        check=True,
        timeout=3600,
    )
    return output_path


@dag(
    dag_id="ddm501_retail_demo_weekly_candidate",
    schedule="0 18 * * 6",  # UTC Saturday 18:00 = Sunday 01:00 Asia/Bangkok.
    start_date=datetime(2026, 10, 3, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "execution_timeout": timedelta(hours=1),
        "on_failure_callback": failure_alert,
    },
    tags=["coursework", "synthetic", "no-production-release"],
)
def retail_demo() -> None:
    """Weekly educational DAG: prepare → search → locked evaluation → demo registry."""

    @task(retries=0)
    def prepare_data() -> str:
        """Generate and validate frozen demo data; deterministic failures are not retried."""
        context = get_current_context()
        logical = context["data_interval_start"].strftime("%Y%m%dT%H%M%S")
        base = Path(os.environ.get("DDM_ARTIFACT_ROOT", "/app/artifacts/airflow"))
        output = base / logical
        output.mkdir(parents=True, exist_ok=True)
        # Metadata DB and model-artifact volume must be persistent across workers.
        return run_stage("prepare", str(output))

    @task
    def train_and_validate(uri: str) -> str:
        """Execute the ten-config protocol; XCom carries a path, not a dataframe."""
        return run_stage("search", uri)

    @task(retries=0)
    def evaluate_locked_candidate(uri: str) -> str:
        """Evaluate exactly the configuration fixed in selection.json."""
        return run_stage("evaluate", uri)

    @task
    def register_demo_candidate(uri: str) -> str:
        """Register a synthetic candidate with deployment_allowed=false."""
        return run_stage("register", uri)

    register_demo_candidate(evaluate_locked_candidate(train_and_validate(prepare_data())))


retail_demo_dag = retail_demo()
