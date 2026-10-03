# DDM501 — Assignment 2

**Nguyễn Minh Trường · 25MS13312**

Bài tiếp nối Assignment 1: thiết kế pipeline/MLOps cho dự báo nhu cầu bán lẻ bảy ngày. Mười cấu hình được thực thi trên **dữ liệu mô phỏng**, với baseline, temporal validation, locked test và MLflow registry cục bộ. Không có triển khai production hoặc bằng chứng tác động kinh doanh.

## Tệp nộp và tài liệu

- [Báo cáo PDF](deliverables/tieng_viet/DDM501_Assignment2_25MS13312_Nguyễn_Minh_Trường.pdf).
- [Word chỉnh sửa](deliverables/tieng_viet/DDM501_Assignment2_25MS13312_Nguyễn_Minh_Trường.docx).
- [Báo cáo Markdown](deliverables/tieng_viet/REPORT.md).
- [Slide PDF tóm tắt — 10 trang, khổ 16:9](deliverables/tieng_viet/slides/DDM501_Assignment2_25MS13312_Nguyen_Minh_Truong_Slides.pdf).
- [Kết quả kiểm tra tài liệu](deliverables/tieng_viet/verification.json).
- `deliverables/tieng_viet/pipeline.*`, `dag.*`: sơ đồ PNG/PDF/Mermaid.

PDF là định dạng nộp theo đề. Word có trường mục lục; dùng **Update Field** khi mở trong Word. PDF có mục lục với số trang và bookmarks.

## Tái lập

Môi trường đã chạy: Windows x64, Python 3.14.7, LightGBM 4.6.0; phiên bản đầy đủ xem `artifacts/environment.json` và `uv.lock`. Exporter dùng phông Times New Roman/Arial/Consolas từ `C:/Windows/Fonts`.

```powershell
uv sync --frozen --cache-dir .uv-cache
$env:PYTHONHASHSEED = '501'
.venv/Scripts/python.exe run_experiments.py --config configs/demo.json --out artifacts
.venv/Scripts/python.exe verify_code.py
.venv/Scripts/python.exe finalize_evidence.py
.venv/Scripts/python.exe build_report.py
.venv/Scripts/python.exe build_slides_vi.py
.venv/Scripts/python.exe verify_report.py
```

Nếu Windows chưa có runtime OpenMP/C++ cho LightGBM, helper `tools/fetch_runtime.py` lấy VCOMP140 x64 từ gói conda-forge với checksum, lưu app-local tại `tools/runtime`. `src/__init__.py` thêm thư mục DLL này vào process, không thay runtime hệ thống. Linux dùng `libgomp1` theo Dockerfile. Helper runtime cần mạng; không phải một phần của thuật toán.

Có thể chạy riêng `--stage prepare|search|evaluate|register`. Chỉ evaluate sau khi đã khóa `selection.json`; register sau khi có test/model artifact. Mỗi lần chạy lại tạo MLflow runs/versions mới; không xem nó là một holdout mới để tiếp tục tuning. Đổi `--out` không tự đổi tracking URI: cấu hình URI hoặc `MLFLOW_TRACKING_URI` riêng nếu muốn tách tracking database.

```powershell
$env:MLFLOW_TRACKING_URI = 'sqlite:///artifacts/mlflow.db'
.venv/Scripts/mlflow.exe ui --backend-store-uri sqlite:///artifacts/mlflow.db --port 5000
```

Lệnh trên chỉ là hướng dẫn mở UI cục bộ; dịch vụ UI không được tự khởi chạy trong quá trình tạo báo cáo.

## Bằng chứng và giới hạn

- `experiment_results.csv`: 10 cấu hình, ba fold và gates.
- `fold_results.csv`: run IDs của lượt kết quả hiện tại; tracking DB có cả các lượt kỹ thuật trước đó.
- `selection.json`: baseline/candidate được chọn bằng validation.
- `test_results.json`, `test_slices.csv`: chỉ candidate và baseline đã khóa.
- `data_manifest.json`: snapshot hashes, generator, seed và coverage.
- `registry.json`: model version/alias, `production_promoted=false`.
- `roundtrip_verification.json`: registry model tải lại cho cùng prediction.
- `code_verification.json`: kết quả pytest, Ruff, format, compile.
- `execution.log`: nhật ký thực thi; PowerShell có thể bao bọc stderr của thư viện thành NativeCommandError dù training đã hoàn tất. Trạng thái MLflow FINISHED và verification là bằng chứng kiểm tra cụ thể.

Nguồn mô phỏng: 4 cửa hàng × 12 SKU × 548 ngày; 48 chuỗi. Schema không dùng latent demand làm nhãn/features. Origin demo cách bảy ngày, label mask loại ngày hết hàng; chưa đại diện toàn bộ weekday-origin và quy mô MVP. Lượt đầu đã được thay thế sau khi sửa purge toàn bộ origin và serialization. Không thay seed, ma trận hoặc ngưỡng theo kết quả test.

DAG `dags/retail_demo.py` dùng Airflow 3 SDK và có task/dependencies cụ thể, nhưng **chưa chạy scheduler**. Airflow cần Linux và shared artifact volume. Dockerfile là mẫu CLI, **chưa build/chạy**. Không có POS, ERP, PostgreSQL serving, load test hoặc pilot cửa hàng thực. Model registry dùng alias `demo_candidate` với `deployment_allowed=false`; không có champion production.

## Quản lý chỉnh sửa

Nội dung gốc: `REPORT_TEMPLATE_VI.md`. `build_report.py` lấy số liệu từ artifacts và snippets từ mã, rồi tạo `REPORT.md`, PDF, Word. Sau khi sửa thuật toán phải chạy lại thực nghiệm, tests và đối chiếu protocol; nếu test đã được xem, không dùng lại nó để chọn hyperparameter mới. Sửa Word trực tiếp không tự cập nhật PDF nguồn.

Chiến lược Git/data/model versioning nằm trong phần 5 báo cáo. Chưa tạo remote repo hoặc release Git; manifests dùng source SHA-256 và ghi rõ Git SHA null. `requirements.lock.txt` có package hashes; base Docker tag và apt packages còn cần pin trong release thực.

Gói ZIP chứa tracking database cục bộ có artifact URI của workspace gốc. Khi giải nén sang thư mục khác, chạy lại pipeline để tạo tracking mới tại đường dẫn đó; không coi URI tuyệt đối trong database cũ là portable.
