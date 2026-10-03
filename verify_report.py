"""Verify exported PDF/Word, rubric coverage, result provenance and model roundtrip."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from docx import Document
import numpy as np
import pandas as pd
import pymupdf

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "deliverables" / "tieng_viet"
ART = ROOT / "artifacts"
pdf_path = next(OUT.glob("DDM501_Assignment2_*.pdf"))
docx_path = next(OUT.glob("DDM501_Assignment2_*.docx"))
document = pymupdf.open(pdf_path)
text = "\n".join(page.get_text() for page in document)
source = (ROOT / "REPORT.md").read_text(encoding="utf-8")
required = [
    "25MS13312",
    "Nguyễn Minh Trường",
    "1. Thiết kế pipeline (25%)",
    "2. Theo dõi thí nghiệm",
    "3. Thiết kế workflow",
    "4. Chất lượng mã",
    "5. Tái lập",
    "Dockerfile",
    "MLflow",
    "Airflow",
    "mô phỏng",
    "E01",
    "E10",
]
checks = {label: label in text for label in required}
checks["no_placeholders"] = not re.search(r"\{\{[^}]+\}\}", source.replace("{{figure:", "FIGURE:"))
checks["word_opens"] = bool(Document(docx_path).paragraphs)
checks["pdf_bookmarks"] = len(document.get_toc()) > 20
checks["pdf_no_replacement_character"] = "\ufffd" not in text
violations = []
blank_pages = []
for page_number, page in enumerate(document, 1):
    if len(page.get_text().strip()) < 60:
        blank_pages.append(page_number)
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                x0, y0, x1, y1 = span["bbox"]
                if x0 < 25 or x1 > page.rect.width - 25 or y0 < 15 or y1 > page.rect.height - 15:
                    violations.append(
                        {"page": page_number, "text": span["text"], "bbox": span["bbox"]}
                    )
checks["no_out_of_page_text"] = not violations
checks["no_blank_pages"] = not blank_pages
data = json.loads((ART / "data_manifest.json").read_text(encoding="utf-8"))
checks["raw_sha256_matches"] = (
    hashlib.sha256((ART / "synthetic_sales.parquet").read_bytes()).hexdigest() == data["raw_sha256"]
)
checks["feature_sha256_matches"] = (
    hashlib.sha256((ART / "examples.parquet").read_bytes()).hexdigest() == data["feature_sha256"]
)
selection = json.loads((ART / "selection.json").read_text(encoding="utf-8"))
result = json.loads((ART / "test_results.json").read_text(encoding="utf-8"))
checks["test_only_locked_models"] = set(result["scores"]) == {
    selection["selected_id"],
    selection["baseline_id"],
}
checks["test_selection_consistent"] = (
    result["selected_id"] == selection["selected_id"] and not selection["test_used_for_selection"]
)
checks["labels_before_test_month"] = pd.Timestamp(result["train_label_max"]) < pd.Timestamp(
    "2025-04-01"
)
for identifier, score in result["scores"].items():
    scored = pd.read_parquet(ART / f"test_predictions_{identifier}.parquet")
    measured = float(100 * (scored.y - scored.prediction).abs().sum() / scored.y.sum())
    checks[f"wape_{identifier}_recomputed"] = bool(np.isclose(measured, score["wape"], atol=1e-10))
    checks[f"wape_{identifier}_in_report"] = f"{score['wape']:.3f}" in text
registry = json.loads((ART / "registry.json").read_text(encoding="utf-8"))
checks["no_production_promotion"] = (
    not registry["production_promoted"] and not result["production_release_authorized"]
)
checks["source_lineage_matches"] = True
environment = json.loads((ART / "environment.json").read_text(encoding="utf-8"))
for relative, digest in environment["source_sha256"].items():
    checks["source_lineage_matches"] &= (
        hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    )
verification = {
    "pdf": pdf_path.name,
    "pages": len(document),
    "bookmarks": len(document.get_toc()),
    "checks": checks,
    "text_violations": violations,
    "blank_pages": blank_pages,
    "pass": bool(all(checks.values())),
    "limits": "Layout/provenance checks; not production certification",
}
(OUT / "verification.json").write_text(
    json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
)
previews = OUT / "previews"
previews.mkdir(exist_ok=True)
for index in [
    0,
    3,
    next(i for i, p in enumerate(document) if "WAPE CV mean" in p.get_text()),
    next(i for i, p in enumerate(document) if "skops_trusted_types" in p.get_text()),
]:
    document[index].get_pixmap(matrix=pymupdf.Matrix(1.15, 1.15)).save(
        str(previews / f"page_{index + 1}.png")
    )
print(
    json.dumps(
        {
            "pages": len(document),
            "pass": verification["pass"],
            "failed": [key for key, value in checks.items() if not value],
            "layout_violations": len(violations),
        },
        ensure_ascii=True,
    )
)
if not verification["pass"]:
    raise SystemExit(1)
