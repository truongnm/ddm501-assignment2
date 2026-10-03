# Rà soát Assignment 2 — 03/10/2026

Đã đối chiếu đủ ba trang đề Assignment 2 và bài Assignment 1 của Nguyễn Minh Trường, MSSV 25MS13312. Báo cáo phiên bản 1.1 giữ nguyên kết quả đo, rút gọn mã trình bày; slide tóm tắt gồm 10 trang.

| Yêu cầu | Vị trí báo cáo | Kết luận |
| --- | --- | --- |
| Tiếp nối Assignment 1 | Phần 0 | Đúng bài toán bán lẻ, một mô hình dùng chung, dự báo 7 ngày, ngày gốc và ngưỡng kế thừa. |
| Pipeline 25% | Phần 1 | Có sơ đồ, đủ 7 stage; purpose/input-output/operations/gates; modularity, recovery và scalability. |
| Experiment/metrics 25% | Phần 2 | Đủ 10 cấu hình, baseline, primary/secondary, business alignment; MLflow logging/registration; bảng kết quả, trade-offs và model recommendation. |
| Orchestration 20% | Phần 3 | Có DAG diagram, tasks/dependencies, trigger/frequency, Airflow snippet, failure/alerting/monitoring. |
| Code quality 20% | Phần 4 | Có style, docstrings, type hints, comments; JSON config, loading và environment overrides. |
| Reproducibility 10% | Phần 5 | Có Git branching/release snippet, data/model versioning, seeds và Dockerfile. |
| Submission | Tệp PDF | Đúng tên DDM501_Assignment2_25MS13312_Nguyễn_Minh_Trường.pdf. |

## Rút gọn theo yêu cầu

- Bỏ khỏi báo cáo phần mã dài của temporal_split và quality_gate; giữ mô tả, ngưỡng và bằng chứng kiểm tra.
- Thay Airflow DAG dài bằng snippet ngắn thể hiện scheduling, task definitions và dependencies; mã đầy đủ vẫn có trong tệp DAG.
- Thay bản chép toàn bộ config loader bằng ví dụ sử dụng typed config và environment override.
- Giữ MLflow setup/logging/registration, Git, seeds và Dockerfile vì đề yêu cầu rõ các snippets này.
- Slide không có code dump; trình bày vấn đề, pipeline, metrics, 10 cấu hình, kết quả, DAG, chất lượng mã, versioning và giới hạn.
- Loại các helper chẩn đoán/trích xuất PDF đã hoàn thành khỏi mã làm việc; giữ mã tái lập thí nghiệm và tạo tài liệu.

## Kiểm chứng

Tám test chống leakage/contracts/metrics/gates đạt; Ruff và kiểm tra compile đạt. PDF báo cáo và slide có kiểm tra nội dung, số liệu, bookmarks và vị trí chữ; kết quả machine-readable ở verification.json tương ứng. Bảng WAPE được tính lại từ prediction artifacts. Model tải lại từ registry có sai khác prediction bằng 0 trong kiểm tra roundtrip đã thực hiện.

Kết quả vẫn được ghi rõ là mô phỏng. Không thay seed, cấu hình, split, metrics hoặc model đã chọn trong lượt rà soát này; chưa chạy thêm training. Airflow scheduler, Docker và hệ thống doanh nghiệp chưa được kiểm chứng tích hợp. Slide là tài liệu thuyết trình bổ sung; báo cáo PDF là sản phẩm nộp chính theo đề.
