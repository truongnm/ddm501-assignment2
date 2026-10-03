# Nội dung slide Assignment 2

## 1. ML Pipeline & MLOps cho dự báo bán lẻ

Assignment 2 · Tóm tắt 10 slide

- Thiết kế: Pipeline 25%; Điều phối Airflow 20%

- Thực nghiệm: Tracking & metrics 25%; 10 cấu hình, chọn trước test

- Tái lập: Chất lượng mã 20%; Versioning 10%

## 2. Bài toán và ràng buộc từ Assignment 1

Bối cảnh · phạm vi

- Quy mô đích: 20 cửa hàng × 2.000 SKU; 40.000 cặp; 280.000 forecast/ngày

- Quyết định: Một mô hình dùng chung; Dự báo h = 1…7; Đơn nháp → người duyệt

- Thời gian: Cutoff dữ liệu 01:00; Công bố trước 05:30; Ngày gốc o = D−1

## 3. Pipeline: đủ bảy stage và cổng chất lượng

Pipeline design · 25%

## 4. Đánh giá đúng thời gian, đúng mục tiêu

Experiment tracking & metrics · 25%

- Protocol chống leakage: CV: tháng 01 / 02 / 03–2025; Test khóa: tháng 04–06–2025; Purge toàn bộ origin; fit trên train; Không dùng target sales/availability làm feature

- Metrics và gates: Primary: WAPE ≤25%; cải thiện ≥10%; Bias tuyệt đối ≤5%; Nhóm không xấu hơn baseline >2 điểm %; Secondary: MAE, RMSE, MASE, coverage, time

## 5. Mười cấu hình có baseline và ablation

Experiment design · ma trận đã định trước


ID | Cấu hình | Mục đích

E01 | Mean 28 ngày | Baseline chính sách hiện tại

E02 | Cùng thứ 4 tuần | Baseline mùa vụ

E03 | Mùa vụ + promo | Hệ số promo chỉ học trên train

E04 | Ridge; alpha=10 | Đối chiếu mô hình đơn giản

E05 | Poisson; 31 lá; lr=0,05 | LightGBM ứng viên chuẩn

E06 | Poisson; 15 lá; lr=0,05 | Giảm capacity so E05

E07 | Poisson; 63 lá; lr=0,05 | Tăng capacity so E05

E08 | Poisson; 31 lá; lr=0,10 | Đổi learning rate so E05

E09 | L1; 31 lá; lr=0,05 | Đổi objective so E05

E10 | Poisson; bỏ promo/price | Ablation khuyến mãi so E05

## 6. Validation: E05 cân bằng sai số và độ phức tạp

Results analysis · kết quả mô phỏng


ID | WAPE pooled % | Bias % | SD 3 fold

E01 | 23.429 | -2.065 | 0.119

E02 | 22.599 | -2.079 | 0.386

E03 | 19.543 | +4.487 | 0.407

E04 | 16.018 | -4.314 | 0.324

E05 | 15.705 | -2.271 | 0.371

E06 | 15.734 | -2.179 | 0.447

E07 | 15.755 | -2.355 | 0.370

E08 | 15.715 | -2.385 | 0.417

E09 | 15.850 | -3.051 | 0.353

E10 | 20.555 | -2.267 | 0.467

- Candidate E05: Poisson · 31 lá · lr=0,05; WAPE validation: 15,705%; Baseline tốt nhất: E03 — 19,543%

## 7. Locked test: candidate vượt baseline đã khóa

Model selection · test tách khỏi tuning


Model | WAPE % | Bias % | MASE

E03 | 20.159 | +6.738 | 0.750

E05 | 15.837 | -2.554 | 0.591

- 21,44%: Cải thiện WAPE tương đối; Model gate đạt; Bias E05: −2,55%

- 3.884 / 4.032: Dòng nhãn đủ điều kiện; Coverage nhãn: 96,33%; Không phải serving coverage

- Bất định: ΔWAPE E05−E03: −4,322 pp; Bootstrap 95%: [-4.74; -3.85]; 12 block tuần; chỉ mô phỏng

## 8. Airflow: tách inference ngày và candidate tuần

Workflow orchestration · 20%

- Schedule: Ngày: chốt 01:00; Cảnh báo nếu trễ 03:30; Deadline 05:30; Candidate: Chủ nhật 01:00

- Recovery: Retry lỗi tạm thời + backoff; Lỗi dữ liệu → quarantine; Task timeout; rollback; XCom chỉ mang artifact URI

- Monitoring: Task/time/freshness/coverage; WAPE/bias khi nhãn đủ tuổi; Drift → điều tra; Alert có owner và runbook

## 9. Mã gọn, cấu hình rõ, lineage có thể tái lập

Code quality 20% · Reproducibility 10%

- Chất lượng mã & MLflow: Style, docstrings, type hints, comments; Config JSON + environment overrides; Log params/metrics/artifacts/signature; 30 fold runs + 1 final run thành công; 8 tests; registry roundtrip không đổi prediction

- Code / data / model versioning: Git branch → review → release tag (thiết kế); Snapshot SHA-256 + split/config/source hashes; Registry version + demo_candidate, pin khi serving; Seed=501; package lock; Dockerfile; Không thay champion từ dữ liệu mô phỏng

## 10. Quyết định và giới hạn bằng chứng

Kết luận · bám sát năm phần rubric

- Đã có bằng chứng: Pipeline đầy đủ, stage gates, recovery; 10 cấu hình + baseline + trade-offs; Selection trước locked test; MLflow logging/registry thực chạy; E05 là candidate phù hợp protocol này

- Cần trước production: Dữ liệu thực và replay origin hằng ngày; Kiểm tra tải, Airflow/Docker và recovery; Shadow + ops gate + người duyệt; Pilot có đối chứng đo stockout/tồn kho; Không suy diễn WAPE thành lợi ích kinh doanh
