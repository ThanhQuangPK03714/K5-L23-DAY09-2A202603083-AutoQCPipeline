"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    thresholds = cfg["label_format"]
    issues = []

    for label_path in ds.label_files():
        stem = label_path.stem
        size = ds.image_size(stem)
        prior_boxes = []

        for line_no, text in enumerate(
            label_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            try:
                cls, cx, cy, width, height = parse_yolo_line(text)
            except ValueError as exc:
                issues.append(Issue(
                    "label_format", ERROR, "BAD_FORMAT", stem,
                    f"dòng {line_no}: định dạng nhãn không hợp lệ ({exc})", line_no,
                ))
                continue

            if not 0 <= cls < len(ds.classes):
                issues.append(Issue(
                    "label_format", ERROR, "BAD_CLASS_ID", stem,
                    f"dòng {line_no}: id lớp {cls} nằm ngoài danh sách lớp", line_no,
                ))
                continue

            if width <= 0 or height <= 0:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_ZERO", stem,
                    f"dòng {line_no}: chiều rộng và chiều cao phải lớn hơn 0", line_no,
                ))
                continue

            box = (cx, cy, width, height)
            left, top = cx - width / 2, cy - height / 2
            right, bottom = cx + width / 2, cy + height / 2
            overflow = max(0.0, -left, -top, right - 1.0, bottom - 1.0)
            if overflow > thresholds["overflow_tol"]:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                    f"dòng {line_no}: box tràn ảnh {overflow:.6g}",
                    line_no, {"overflow": overflow},
                ))

            for prior_cls, prior_box in prior_boxes:
                if prior_cls == cls and iou_xywh(box, prior_box) > thresholds["dup_box_iou"]:
                    issues.append(Issue(
                        "label_format", ERROR, "DUP_BOX", stem,
                        f"dòng {line_no}: box trùng với một nhãn trước đó", line_no,
                    ))
                    break
            prior_boxes.append((cls, box))

            if size is not None:
                image_width, image_height = size
                if min(width * image_width, height * image_height) < thresholds["min_box_px"]:
                    issues.append(Issue(
                        "label_format", WARN, "BOX_TINY", stem,
                        f"dòng {line_no}: cạnh ngắn của box nhỏ hơn {thresholds['min_box_px']} px",
                        line_no,
                    ))

            if width * height > thresholds["max_box_frac"]:
                issues.append(Issue(
                    "label_format", WARN, "BOX_HUGE", stem,
                    f"dòng {line_no}: box chiếm {width * height:.6g} diện tích chuẩn hóa",
                    line_no,
                ))

    return issues
