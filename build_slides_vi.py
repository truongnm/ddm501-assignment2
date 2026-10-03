"""Export ten concise, code-free summary slides from verified report evidence."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from PIL import Image, ImageDraw
import pymupdf
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "deliverables" / "tieng_viet" / "slides"
OUT.mkdir(parents=True, exist_ok=True)
ART = ROOT / "artifacts"
W, H = 960, 540
FONT = Path("C:/Windows/Fonts")
for name, filename in [("Slide", "arial.ttf"), ("Slide-Bold", "arialbd.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONT / filename)))
pdfmetrics.registerFontFamily("Slide", normal="Slide", bold="Slide-Bold")
NAVY = colors.HexColor("#163548")
TEAL = colors.HexColor("#137986")
MUTED = colors.HexColor("#586b7c")
PALE = colors.HexColor("#e6f1f3")
PAPER = colors.HexColor("#f7f9fb")
selection = json.loads((ART / "selection.json").read_text(encoding="utf-8"))
test = json.loads((ART / "test_results.json").read_text(encoding="utf-8"))
data = json.loads((ART / "data_manifest.json").read_text(encoding="utf-8"))
results = pd.read_csv(ART / "experiment_results.csv").set_index("id")
chosen, baseline = test["selected_id"], test["baseline_id"]
model_score, base_score = test["scores"][chosen], test["scores"][baseline]
PDF = OUT / "DDM501_Assignment2_25MS13312_Nguyen_Minh_Truong_Slides.pdf"
c = canvas.Canvas(str(PDF), pagesize=(W, H))
c.setTitle("DDM501 Assignment 2 — Tóm tắt ML Pipeline & MLOps")
c.setAuthor("Nguyễn Minh Trường")
slide_count = 0
notes: list[str] = []
layout_errors: list[str] = []


def paragraph(
    text: str, x: float, top: float, width: float, size: float = 16, bold: bool = False, color=NAVY
) -> float:
    """Wrap Vietnamese text and record any drawing outside the usable slide area."""
    style = ParagraphStyle(
        "slide",
        fontName="Slide-Bold" if bold else "Slide",
        fontSize=size,
        leading=size * 1.35,
        textColor=color,
    )
    text = escape(text).replace("\n", "<br/>")
    p = Paragraph(text, style)
    _, height = p.wrap(width, H)
    if top - height < 43 or top > H - 10:
        layout_errors.append(f"Slide {slide_count}: text outside safe area: {text[:60]}")
    p.drawOn(c, x, top - height)
    return height


def start(title: str, label: str, source: str = "Nguồn: báo cáo và artifacts đi kèm") -> None:
    """Create a consistent numbered slide, footer and PDF outline entry."""
    global slide_count
    slide_count += 1
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.rect(0, H - 7, W, 7, fill=1, stroke=0)
    paragraph(label.upper(), 42, 506, 880, 10, True, TEAL)
    paragraph(title, 42, 475, 880, 27, True)
    c.setStrokeColor(colors.HexColor("#d7e2e9"))
    c.line(42, 39, 918, 39)
    c.setFont("Slide", 8)
    c.setFillColor(MUTED)
    c.drawString(42, 23, "DDM501 · Nguyễn Minh Trường · 25MS13312")
    c.drawCentredString(560, 23, source)
    c.drawRightString(918, 23, f"{slide_count:02d} / 10")
    c.bookmarkPage(f"slide-{slide_count}")
    c.addOutlineEntry(title, f"slide-{slide_count}", level=0)
    notes.append(f"## {slide_count}. {title}\n\n{label}\n")


def card(x: float, y: float, width: float, height: float, title: str, body: str) -> None:
    """Draw a compact concept card with generous separation from surrounding content."""
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#dce6ec"))
    c.roundRect(x, y, width, height, 10, fill=1, stroke=1)
    paragraph(title, x + 18, y + height - 17, width - 36, 18, True, TEAL)
    paragraph(body, x + 18, y + height - 53, width - 36, 15)
    notes.append(f"- {title}: {body.replace(chr(10), '; ')}\n")


def box(x: float, y: float, width: float, title: str, detail: str, height: float = 76) -> None:
    """A pipeline/DAG node with a short input/output description."""
    c.setFillColor(PALE)
    c.setStrokeColor(colors.HexColor("#a0c4cb"))
    c.roundRect(x, y, width, height, 8, fill=1, stroke=1)
    paragraph(title, x + 12, y + height - 12, width - 24, 14, True)
    paragraph(detail, x + 12, y + height - 38, width - 24, 12, color=MUTED)


def arrow(x1: float, y1: float, x2: float, y2: float) -> None:
    """Horizontal dependency arrow."""
    c.setStrokeColor(TEAL)
    c.setLineWidth(1.8)
    c.line(x1, y1, x2, y2)
    c.line(x2, y2, x2 - 6, y2 + 4)
    c.line(x2, y2, x2 - 6, y2 - 4)


def table(
    headers: list[str],
    rows: list[list[str]],
    x: float,
    top: float,
    widths: list[float],
    row_height: float = 27,
    highlight: str | None = None,
) -> None:
    """Draw readable tabular comparisons; do not rasterize code or text."""
    for row_index, row in enumerate([headers] + rows):
        y = top - (row_index + 1) * row_height
        fill = PALE if row_index == 0 else (colors.white if row_index % 2 else PAPER)
        if highlight and row[0] == highlight:
            fill = colors.HexColor("#cfebe4")
        c.setFillColor(fill)
        c.rect(x, y, sum(widths), row_height, fill=1, stroke=0)
        offset = x
        for value, width in zip(row, widths):
            paragraph(
                value,
                offset + 9,
                y + row_height - 6,
                width - 16,
                12,
                row_index == 0 or (highlight is not None and row[0] == highlight),
            )
            offset += width
    notes.append("\n" + " | ".join(headers) + "\n")
    notes.extend(" | ".join(row) + "\n" for row in rows)


start("ML Pipeline & MLOps cho dự báo bán lẻ", "Assignment 2 · Tóm tắt 10 slide")
paragraph("Tiếp nối Assignment 1: dự báo bảy ngày,\nđơn nháp có người duyệt.", 44, 398, 850, 23)
card(42, 166, 278, 145, "Thiết kế", "Pipeline 25%\nĐiều phối Airflow 20%")
card(341, 166, 278, 145, "Thực nghiệm", "Tracking & metrics 25%\n10 cấu hình, chọn trước test")
card(640, 166, 278, 145, "Tái lập", "Chất lượng mã 20%\nVersioning 10%")
paragraph(
    "Kết quả dùng dữ liệu mô phỏng; không phải bằng chứng triển khai doanh nghiệp.",
    44,
    123,
    860,
    16,
    color=TEAL,
)
c.showPage()

start(
    "Bài toán và ràng buộc từ Assignment 1",
    "Bối cảnh · phạm vi",
    "Nguồn: Assignment 1, mục 1.7, 2.3, 3.3",
)
card(42, 217, 278, 190, "Quy mô đích", "20 cửa hàng × 2.000 SKU\n40.000 cặp\n280.000 forecast/ngày")
card(
    341,
    217,
    278,
    190,
    "Quyết định",
    "Một mô hình dùng chung\nDự báo h = 1…7\nĐơn nháp → người duyệt",
)
card(640, 217, 278, 190, "Thời gian", "Cutoff dữ liệu 01:00\nCông bố trước 05:30\nNgày gốc o = D−1")
paragraph(
    "Mục tiêu: giảm hết hàng và tồn kho dư. Sai số forecast là chỉ số trung gian;\n"
    "tác động kinh doanh vẫn cần pilot có nhóm đối chứng.",
    44,
    163,
    860,
    19,
)
c.showPage()

start("Pipeline: đủ bảy stage và cổng chất lượng", "Pipeline design · 25%")
nodes = [
    (42, 317, "1. Ingestion", "POS/plans → raw + hash"),
    (268, 317, "2. Validation", "Schema, keys, coverage"),
    (494, 317, "3. Preprocessing", "Fit transformer trên train"),
    (720, 317, "4. Features", "History ≤ o; plans đã biết"),
    (42, 185, "5. Training", "10 cấu hình; temporal CV"),
    (268, 185, "6. Evaluation", "Lock selection → test"),
    (494, 185, "7. Deployment", "Registry → staging → duyệt"),
    (720, 185, "Batch & monitoring", "Pin version; labels đủ tuổi"),
]
for x, y, title, detail in nodes:
    box(x, y, 198, title, detail)
for y in [355, 223]:
    for x in [240, 466, 692]:
        arrow(x, y, x + 28, y)
c.setStrokeColor(TEAL)
c.line(819, 317, 819, 289)
c.line(819, 289, 141, 289)
c.line(141, 289, 141, 261)
c.line(141, 261, 137, 267)
c.line(141, 261, 145, 267)
paragraph(
    "Gates: dữ liệu hợp lệ → model đạt ngưỡng → ops/shadow đạt → người duyệt release.",
    44,
    138,
    870,
    17,
    True,
)
paragraph(
    "Module tái sử dụng; partition theo cửa hàng; lỗi dữ liệu cách ly, lỗi tạm thời retry; rollback version.",
    44,
    101,
    870,
    14,
    color=MUTED,
)
c.showPage()

start(
    "Đánh giá đúng thời gian, đúng mục tiêu",
    "Experiment tracking & metrics · 25%",
    "Nguồn: protocol + configs/demo.json",
)
card(
    42,
    211,
    420,
    196,
    "Protocol chống leakage",
    "CV: tháng 01 / 02 / 03–2025\nTest khóa: tháng 04–06–2025\nPurge toàn bộ origin; fit trên train\nKhông dùng target sales/availability làm feature",
)
card(
    484,
    211,
    434,
    196,
    "Metrics và gates",
    "Primary: WAPE ≤25%; cải thiện ≥10%\nBias tuyệt đối ≤5%\nNhóm không xấu hơn baseline >2 điểm %\nSecondary: MAE, RMSE, MASE, coverage, time",
)
paragraph("WAPE = 100 × Σ|y−f| / Σy; bias = 100 × Σ(f−y) / Σy.", 44, 167, 860, 18)
paragraph(
    "WAPE tốt chưa chứng minh giảm hết hàng: còn phụ thuộc tồn kho, lead time và chính sách đặt hàng.",
    44,
    123,
    860,
    16,
    color=TEAL,
)
c.showPage()

start(
    "Mười cấu hình có baseline và ablation",
    "Experiment design · ma trận đã định trước",
    "Nguồn: experiment_matrix.json",
)
rows = [
    ["E01", "Mean 28 ngày", "Baseline chính sách hiện tại"],
    ["E02", "Cùng thứ 4 tuần", "Baseline mùa vụ"],
    ["E03", "Mùa vụ + promo", "Hệ số promo chỉ học trên train"],
    ["E04", "Ridge; alpha=10", "Đối chiếu mô hình đơn giản"],
    ["E05", "Poisson; 31 lá; lr=0,05", "LightGBM ứng viên chuẩn"],
    ["E06", "Poisson; 15 lá; lr=0,05", "Giảm capacity so E05"],
    ["E07", "Poisson; 63 lá; lr=0,05", "Tăng capacity so E05"],
    ["E08", "Poisson; 31 lá; lr=0,10", "Đổi learning rate so E05"],
    ["E09", "L1; 31 lá; lr=0,05", "Đổi objective so E05"],
    ["E10", "Poisson; bỏ promo/price", "Ablation khuyến mãi so E05"],
]
table(["ID", "Cấu hình", "Mục đích"], rows, 42, 408, [72, 365, 439], 27)
paragraph(
    "Cùng split/mask; LightGBM: 200 cây, 2 luồng, seed=501. Preprocessing học riêng từng fold.",
    44,
    88,
    870,
    13,
    color=MUTED,
)
c.showPage()

start(
    "Validation: E05 cân bằng sai số và độ phức tạp",
    "Results analysis · kết quả mô phỏng",
    "Nguồn: experiment_results.csv",
)
rows = [
    [i, f"{r.wape:.3f}", f"{r.bias:+.3f}", f"{r.wape_cv_sd:.3f}"] for i, r in results.iterrows()
]
table(
    ["ID", "WAPE pooled %", "Bias %", "SD 3 fold"], rows, 42, 407, [55, 145, 110, 115], 27, chosen
)
card(
    493,
    257,
    425,
    150,
    "Candidate E05",
    "Poisson · 31 lá · lr=0,05\nWAPE validation: 15,705%\nBaseline tốt nhất: E03 — 19,543%",
)
promo_delta = results.loc["E10", "wape"] - results.loc["E05", "wape"]
paragraph(
    f"Bỏ promo/price: WAPE tăng {promo_delta:.3f} điểm %.\n"
    "63 lá không cải thiện so với 31 lá.\n"
    "Ridge nhanh hơn; chênh nhỏ giữa các LGBM\nkhông chứng minh ưu thế thống kê chắc chắn.",
    504,
    232,
    398,
    15,
)
paragraph(
    "Chọn cấu hình bằng validation; các model dùng cùng dòng nhãn đủ điều kiện.",
    44,
    88,
    870,
    13,
    color=MUTED,
)
c.showPage()

start(
    "Locked test: candidate vượt baseline đã khóa",
    "Model selection · test tách khỏi tuning",
    "Nguồn: test_results.json; test_slices.csv",
)
table(
    ["Model", "WAPE %", "Bias %", "MASE"],
    [
        [
            baseline,
            f"{base_score['wape']:.3f}",
            f"{base_score['bias']:+.3f}",
            f"{base_score['mase']:.3f}",
        ],
        [
            chosen,
            f"{model_score['wape']:.3f}",
            f"{model_score['bias']:+.3f}",
            f"{model_score['mase']:.3f}",
        ],
    ],
    42,
    400,
    [164, 225, 225, 262],
    42,
    chosen,
)
card(42, 125, 278, 138, "21,44%", "Cải thiện WAPE tương đối\nModel gate đạt\nBias E05: −2,55%")
card(
    341,
    125,
    278,
    138,
    "3.884 / 4.032",
    "Dòng nhãn đủ điều kiện\nCoverage nhãn: 96,33%\nKhông phải serving coverage",
)
ci = test["uncertainty"]["difference_wape_pp_95ci"]
card(
    640,
    125,
    278,
    138,
    "Bất định",
    f"ΔWAPE E05−E03: −4,322 pp\nBootstrap 95%: [{ci[0]:.2f}; {ci[1]:.2f}]\n12 block tuần; chỉ mô phỏng",
)
paragraph(
    "Khuyến nghị E05 làm candidate nghiên cứu; chưa cho phép phát hành production.",
    44,
    90,
    870,
    16,
    True,
    TEAL,
)
c.showPage()

start(
    "Airflow: tách inference ngày và candidate tuần",
    "Workflow orchestration · 20%",
    "Nguồn: DAG design; dags/retail_demo.py",
)
paragraph(
    "DAG ngày: ingest → validate → features → predict → gate → publish", 44, 407, 870, 18, True
)
paragraph(
    "DAG tuần: snapshot/split → train/CV → lock/evaluate → registry → review", 44, 364, 870, 17
)
card(
    42,
    143,
    278,
    165,
    "Schedule",
    "Ngày: chốt 01:00\nCảnh báo nếu trễ 03:30\nDeadline 05:30\nCandidate: Chủ nhật 01:00",
)
card(
    341,
    143,
    278,
    165,
    "Recovery",
    "Retry lỗi tạm thời + backoff\nLỗi dữ liệu → quarantine\nTask timeout; rollback\nXCom chỉ mang artifact URI",
)
card(
    640,
    143,
    278,
    165,
    "Monitoring",
    "Task/time/freshness/coverage\nWAPE/bias khi nhãn đủ tuổi\nDrift → điều tra\nAlert có owner và runbook",
)
paragraph(
    "DAG demo: prepare → search → evaluate → register; đã kiểm tra cú pháp, chưa chạy scheduler.",
    44,
    94,
    870,
    14,
    color=MUTED,
)
c.showPage()

start("Mã gọn, cấu hình rõ, lineage có thể tái lập", "Code quality 20% · Reproducibility 10%")
card(
    42,
    195,
    420,
    210,
    "Chất lượng mã & MLflow",
    "Style, docstrings, type hints, comments\nConfig JSON + environment overrides\nLog params/metrics/artifacts/signature\n30 fold runs + 1 final run thành công\n8 tests; registry roundtrip không đổi prediction",
)
card(
    484,
    195,
    434,
    210,
    "Code / data / model versioning",
    "Git branch → review → release tag (thiết kế)\nSnapshot SHA-256 + split/config/source hashes\nRegistry version + demo_candidate, pin khi serving\nSeed=501; package lock; Dockerfile\nKhông thay champion từ dữ liệu mô phỏng",
)
paragraph(
    "Báo cáo chỉ giữ snippets bắt buộc: MLflow, DAG/tasks/dependencies, config, seed, Git, Dockerfile.",
    44,
    147,
    870,
    16,
)
paragraph(
    "Airflow integration và Docker build chưa thực hiện; seed không bảo đảm giống hệt mọi phần cứng.",
    44,
    102,
    870,
    14,
    color=MUTED,
)
c.showPage()

start("Quyết định và giới hạn bằng chứng", "Kết luận · bám sát năm phần rubric")
card(
    42,
    193,
    420,
    212,
    "Đã có bằng chứng",
    "Pipeline đầy đủ, stage gates, recovery\n10 cấu hình + baseline + trade-offs\nSelection trước locked test\nMLflow logging/registry thực chạy\nE05 là candidate phù hợp protocol này",
)
card(
    484,
    193,
    434,
    212,
    "Cần trước production",
    "Dữ liệu thực và replay origin hằng ngày\nKiểm tra tải, Airflow/Docker và recovery\nShadow + ops gate + người duyệt\nPilot có đối chứng đo stockout/tồn kho\nKhông suy diễn WAPE thành lợi ích kinh doanh",
)
paragraph(
    f"Demo: {data['series']} chuỗi; một seed; origin cách bảy ngày; chưa đại diện đầy đủ vận hành thực.",
    44,
    145,
    870,
    15,
    color=MUTED,
)
paragraph(
    "Nguồn phương pháp: Forecasting: Principles and Practice; MLflow; Airflow; LightGBM.\n"
    "Trích dẫn chi tiết và toàn bộ kết quả nằm trong báo cáo Assignment 2.",
    44,
    106,
    870,
    13,
    color=MUTED,
)
c.showPage()
c.save()
(OUT / "NOI_DUNG_SLIDE.md").write_text(
    "# Nội dung slide Assignment 2\n\n" + "\n".join(notes), encoding="utf-8"
)

document = pymupdf.open(PDF)
text = "\n".join(page.get_text() for page in document)
overflow = []
for index, page in enumerate(document, 1):
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                x0, y0, x1, y1 = span["bbox"]
                if x0 < 20 or x1 > W - 20 or y0 < 12 or y1 > H - 12:
                    overflow.append({"slide": index, "text": span["text"]})
checks = {
    "10_slides": len(document) == 10,
    "16_9": all(abs(page.rect.width / page.rect.height - 16 / 9) < 1e-8 for page in document),
    "rubric_covered": all(
        label in text for label in ["25%", "20%", "10%", "Airflow", "MLflow", "Versioning"]
    ),
    "ten_experiments": all(f"E{i:02d}" in text for i in range(1, 11)),
    "test_scores_match": f"{model_score['wape']:.3f}" in text
    and f"{base_score['wape']:.3f}" in text,
    "synthetic_explicit": "mô phỏng" in text,
    "no_code_dump": "def " not in text and "import " not in text,
    "no_overflow": not overflow and not layout_errors,
    "bookmarks": len(document.get_toc()) == 10,
}
verification = {
    "pages": len(document),
    "checks": checks,
    "overflow": overflow,
    "layout_errors": layout_errors,
    "pass": all(checks.values()),
}
(OUT / "verification.json").write_text(
    json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
)
thumbs = []
for index, page in enumerate(document):
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5))
    thumbs.append(Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples))
    if index in [2, 5, 6, 8]:
        page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(str(OUT / f"slide_{index + 1}.png"))
sheet = Image.new("RGB", (1000, 5 * 292 + 20), "#dfe7ed")
draw = ImageDraw.Draw(sheet)
for index, thumb in enumerate(thumbs):
    x, y = 10 + (index % 2) * 495, 10 + (index // 2) * 292
    sheet.paste(thumb, (x, y))
    draw.text((x + 4, y + 273), str(index + 1), fill="#163548")
sheet.save(OUT / "slide_preview.png")
print(
    json.dumps(
        {
            "slides": len(document),
            "pass": verification["pass"],
            "failed": [key for key, value in checks.items() if not value],
        },
        ensure_ascii=True,
    )
)
if not verification["pass"]:
    raise SystemExit(1)
