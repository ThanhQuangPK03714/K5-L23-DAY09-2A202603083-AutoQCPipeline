# Báo cáo Day 09

## 1. Kết luận trước

Pipeline kết luận **Release**. Bước intake quét 224 ảnh, loại 31 ảnh lỗi/trùng/rò rỉ và đưa 193 ảnh vào QC; manifest xuất `clean_v1` cũng ghi nhận 193 ảnh. Sau mô phỏng duyệt 80 ảnh, còn 0 lỗi bắt buộc và 13/193 ảnh có cảnh báo (6,74%), thấp hơn ngưỡng Hold 10%.

## 2. Lỗi và phân việc

Theo `01_intake` và `02_error_list_v1`:

| Mã lỗi | Số phát hiện | Xử lý |
|---|---:|---|
| `BAD_SIZE` 3, `CORRUPT_IMAGE` 2, `DUP_IMAGE_EXACT` 8, `DUP_IMAGE_NEAR` 7, `LEAK_TEST` 11 | 31 ảnh | Máy loại ở intake; 193/224 ảnh được nhận. |
| `BAD_CLASS_ID` 6, `BAD_FORMAT` 3, `BOX_ZERO` 4, `DUP_BOX` 7 | 20 dòng | Autofix xóa dòng lỗi. |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Autofix cắt box vào ảnh. |
| `BAD_CLASS_NAME` | 2 lỗi trong 1 `data.yaml` | Autofix ghi lại tên lớp chuẩn một lần. |
| `MISSING_LABEL_FILE` | 6 ảnh | Máy đưa vào hàng đợi `needs_label`; cần người gán, không tạo nhãn rỗng. |

Các cảnh báo không được autofix: `BOX_HUGE` 3; `BOX_TINY` 6 dòng/4 ảnh; `CLASS_RARE` 4 cảnh báo cấp dataset; `EMPTY_LABEL` 11 ảnh; `POSSIBLE_FALSE_POS` 28 dòng/26 ảnh; `POSSIBLE_LOOSE_BOX` 11 ảnh; `POSSIBLE_MISSING` 32 ảnh; `POSSIBLE_WRONG_CLASS` 13 ảnh. Đây là gợi ý cho người kiểm, không phải kết luận chắc chắn của model. Hàng đợi có 98 ảnh; mô phỏng đã duyệt 80 theo ngân sách. Trong 80 ảnh đó, 67 ảnh có ít nhất một cảnh báo ngữ nghĩa: `POSSIBLE_MISSING` 32, `POSSIBLE_WRONG_CLASS` 13, `POSSIBLE_FALSE_POS` 20 và `POSSIBLE_LOOSE_BOX` 11; các nhóm có thể trùng ảnh.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 16 | `DUP_IMAGE_NEAR`: 1.00/0.50 → 1.00/0.83; `DUP_IMAGE_EXACT`: 1.00/1.00 → 1.00/1.00 | Near-duplicate F1 tăng 0.67 → 0.91, không có FP trong calibration. Tránh 20: exact recall giảm còn 0.33. |
| `second_opinion.conf` | 0.25 | 0.8 | `WRONG_CLASS`: 0.56/0.83 → 1.00/0.83; `MISSING`: 0.50/1.00 → 0.67/0.75; `LOOSE_BOX`: 0.29/0.40 → 0.50/0.20; `FALSE_POS`: 0.31/1.00 → 0.31/1.00 | 0.8 cho macro-F1 cao nhất trong sweep (0.594; trước 0.536) và giảm báo động giả ở wrong-class. Đánh đổi: bỏ sót 2/8 lỗi missing và recall loose-box chỉ còn 0.20. |

**Giới hạn của calibration:** bộ này chỉ có 6 lỗi near-duplicate và 3 exact-duplicate được chèn, nên mỗi trường hợp ảnh hưởng đáng kể đến recall; 16 là lựa chọn tốt nhất trong sweep chứ chưa đảm bảo ngưỡng tối ưu trên mọi ảnh thực tế. Cần kiểm tra trực quan các cặp ảnh bị gắn cờ ở lô raw trước khi loại ảnh.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

Đã chạy `python -X utf8 -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: không có ảnh được duyệt, kết quả là **Rework**, mã thoát **20**, còn 6 lỗi `MISSING_LABEL_FILE`, và `exported` là `null` (không xuất dataset). Đây chứng minh gate chặn lô chưa được gán nhãn.

Hai điểm mù được thể hiện trong calibration:

1. Với `conf=0.8`, check chỉ phát hiện 6/8 lỗi `POSSIBLE_MISSING` (recall 0.75) và 1/5 `POSSIBLE_LOOSE_BOX` (recall 0.20); box bỏ sót hoặc lỏng vẫn có thể qua nếu model không phát hiện đủ tin cậy.
2. `POSSIBLE_FALSE_POS` có precision 0.31 (5 TP, 11 FP) trong calibration. Model lớn có thể bất đồng với nhãn đúng hoặc tự dự đoán sai, nên cảnh báo cần người xem ảnh chứ không thể tự động xem là lỗi thật.

## 5. Train: raw vs clean

Đã train CPU rút gọn bằng `yolo26n.pt`, 15 epoch, ảnh 416px, batch 16; hai biến thể dùng cùng seed 0 và 1, cùng val `gold_val` và test. Raw dùng 224 ảnh train; Clean dùng 193 ảnh theo export pipeline. Đây là cấu hình rút gọn theo hướng dẫn, không phải cấu hình chuẩn Colab 20 epoch/640px.

| Biến thể | Ảnh train | mAP50 (TB ± SD) | mAP50-95 (TB ± SD) | Precision (TB ± SD) | Recall (TB ± SD) |
|---|---:|---:|---:|---:|---:|
| Raw | 224 | 0.621 ± 0.006 | 0.419 ± 0.018 | 0.639 ± 0.002 | 0.577 ± 0.013 |
| Clean | 193 | 0.638 ± 0.049 | 0.414 ± 0.034 | 0.734 ± 0.043 | 0.515 ± 0.001 |

Clean cao hơn Raw **0.017 mAP50**, nhưng mức chênh này nhỏ hơn độ lệch giữa seed của Clean (SD 0.049); với chỉ hai seed, chưa thể kết luận pipeline làm tăng mAP một cách ổn định. mAP50-95 của Clean thấp hơn 0.005; precision tăng 0.095 trong khi recall giảm 0.062. Kết quả và cấu hình từng seed được lưu trong `submission/results/`, bảng tổng hợp trong `comparison.md`.

## 6. Quyết định và ghi chú AI

**Quyết định:** theo kết quả chạy hiện tại, phát hành `clean_v1` là **Release**; 13/193 ảnh còn cảnh báo nằm dưới ngưỡng Hold. Các cảnh báo ngữ nghĩa vẫn cần được xác nhận khi sử dụng dữ liệu.

- **Dùng AI:** có; prompt chính là hoàn thiện 4 module Python của pipeline theo quy tắc và test có sẵn.
- **Kiểm tra:** toàn bộ pytest **79/79 PASS** (`python scripts/check_submission.py`); checker đầy đủ xác nhận 0 lỗi, 0 cảnh báo; đồng thời đối chiếu báo cáo pipeline, manifest export và thử gate với ngân sách 0.
- **Lần AI sai:** autofix ban đầu ghi newline khi xóa dòng lỗi duy nhất, làm phát sinh `BAD_FORMAT` giả; đã sửa và xác nhận lại bằng kiểm thử gate.
