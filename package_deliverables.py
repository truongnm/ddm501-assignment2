"""Package reviewable source, reports and measured evidence without environment caches."""

from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
output = root / "deliverables" / "DDM501_Assignment2_25MS13312_MaNguon_KetQua.zip"
roots = ["src", "dags", "tests", "configs", "artifacts", "mlruns", "deliverables/tieng_viet"]
files = [
    root / name
    for name in [
        "README.md",
        "pyproject.toml",
        "uv.lock",
        "requirements.lock.txt",
        "Dockerfile",
        "run_experiments.py",
        "build_report.py",
        "build_slides_vi.py",
        "verify_code.py",
        "verify_report.py",
        "finalize_evidence.py",
        "REPORT_TEMPLATE_VI.md",
        "REPORT.md",
        "package_deliverables.py",
    ]
]
files += [root / "tools" / "fetch_runtime.py", root / "tools" / "runtime" / "provenance.json"]
for name in roots:
    directory = root / name
    if directory.exists():
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and not any(
                part in ["__pycache__", "matplotlib", "roundtrip", "previews", "superseded"]
                for part in path.relative_to(root).parts
            )
        )
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(set(files)):
        if path.exists():
            archive.write(path, path.relative_to(root).as_posix())
with zipfile.ZipFile(output) as archive:
    bad = archive.testzip()
    if bad:
        raise ValueError(f"Archive checksum failed: {bad}")
print(f"Packaged {len(files)} files; {output.stat().st_size:,} bytes")
