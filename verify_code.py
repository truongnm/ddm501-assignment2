"""Run meaningful code checks and emit a reportable, machine-readable evidence file."""

from __future__ import annotations

import json
from pathlib import Path
import py_compile
import subprocess
import sys

root = Path(__file__).resolve().parent
artifacts = root / "artifacts"
artifacts.mkdir(exist_ok=True)
commands = {
    "pytest": [sys.executable, "-m", "pytest", "-q"],
    "ruff": [
        str(Path(sys.executable).with_name("ruff.exe")),
        "check",
        "src",
        "tests",
        "run_experiments.py",
        "dags",
        "build_report.py",
        "verify_code.py",
        "verify_report.py",
    ],
    "format": [
        str(Path(sys.executable).with_name("ruff.exe")),
        "format",
        "--check",
        "src",
        "tests",
        "run_experiments.py",
        "dags",
        "build_report.py",
        "verify_code.py",
        "verify_report.py",
    ],
}
results = {}
for name, command in commands.items():
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    (artifacts / (name + ".log")).write_text(completed.stdout + completed.stderr, encoding="utf-8")
    results[name] = {"returncode": completed.returncode, "stdout": completed.stdout.strip()}
files = [
    root / "run_experiments.py",
    root / "build_report.py",
    root / "verify_code.py",
    root / "verify_report.py",
    root / "dags" / "retail_demo.py",
    root / "src" / "forecasting.py",
]
for path in files:
    py_compile.compile(str(path), doraise=True)
pytest_summary = results["pytest"]["stdout"].splitlines()[-1]
value = {
    "pytest_summary": pytest_summary,
    "ruff_summary": "All checks passed; Ruff format passed"
    if all(results[x]["returncode"] == 0 for x in ["ruff", "format"])
    else "FAILED",
    "compile_summary": f"Compiled {len(files)} Python files, including DAG definition",
    "checks": results,
}
(artifacts / "code_verification.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
print(pytest_summary)
if not all(result["returncode"] == 0 for result in results.values()):
    raise SystemExit("Code checks failed; see artifacts/*.log")
print("All code checks passed")
