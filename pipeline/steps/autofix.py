"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    active = [issue for issue in issues if issue.severity == ERROR]
    fixes = []
    removed_images = set()

    def is_remove_image(code):
        return (
            code.startswith("DUP_IMAGE_")
            or code in {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
        )

    for issue in active:
        if not is_remove_image(issue.code) or issue.image in removed_images:
            continue
        image_path = ds.image_path(issue.image)
        label_path = ds.label_path(issue.image)
        if image_path is None and not label_path.exists():
            continue
        if image_path is not None:
            image_path.unlink()
        if label_path.exists():
            label_path.unlink()
        removed_images.add(issue.image)
        fixes.append({
            "image": issue.image,
            "line": "",
            "action": "remove_image",
            "before": "ảnh và nhãn",
            "after": "đã xóa khỏi dataset",
        })

    for issue in active:
        if issue.code == "MISSING_LABEL_FILE" and issue.image not in removed_images:
            fixes.append({
                "image": issue.image,
                "line": "",
                "action": "needs_label",
                "before": "(không có file)",
                "after": "chuyển người gán",
            })

    if any(issue.code == "BAD_CLASS_NAME" for issue in active):
        yaml_path = ds.yaml_path
        document = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) if yaml_path.exists() else {}
        document = document or {}
        if not isinstance(document, dict):
            document = {}
        expected_names = {index: name for index, name in enumerate(cfg["classes"])}
        if ds.yaml_names() != expected_names:
            before = document.get("names", "")
            document["names"] = expected_names
            yaml_path.parent.mkdir(parents=True, exist_ok=True)
            yaml_path.write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": str(before),
                "after": str(cfg["classes"]),
            })

    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    drop_lines = defaultdict(dict)
    clip_lines = defaultdict(dict)
    for issue in active:
        if issue.image in removed_images or issue.line is None:
            continue
        if issue.code in drop_codes:
            drop_lines[issue.image][issue.line] = issue
        elif issue.code == "BOX_OUT_OF_IMAGE":
            clip_lines[issue.image][issue.line] = issue

    for stem in dict.fromkeys(
        [issue.image for issue in active if issue.line is not None and issue.image not in removed_images]
    ):
        label_path = ds.label_path(stem)
        if not label_path.exists():
            continue
        original_lines = label_path.read_text(encoding="utf-8", errors="replace").splitlines()
        line_actions = []
        for line_no in sorted(set(drop_lines[stem]) | set(clip_lines[stem])):
            if not 1 <= line_no <= len(original_lines):
                continue
            before = original_lines[line_no - 1]
            if line_no in drop_lines[stem]:
                line_actions.append((line_no, "drop_line", before, ""))
                continue

            try:
                cls, cx, cy, width, height = parse_yolo_line(before)
            except ValueError:
                continue
            x1, y1 = max(0.0, cx - width / 2), max(0.0, cy - height / 2)
            x2, y2 = min(1.0, cx + width / 2), min(1.0, cy + height / 2)
            if x2 <= x1 or y2 <= y1:
                line_actions.append((line_no, "drop_line", before, ""))
            else:
                after = (
                    f"{cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} "
                    f"{x2 - x1:.6f} {y2 - y1:.6f}"
                )
                line_actions.append((line_no, "clip_box", before, after))

        if not line_actions:
            continue
        changed_lines = list(original_lines)
        for line_no, action, before, after in line_actions:
            if action == "drop_line":
                changed_lines[line_no - 1] = None
            else:
                changed_lines[line_no - 1] = after
            fixes.append({
                "image": stem,
                "line": line_no,
                "action": action,
                "before": before,
                "after": after,
            })
        remaining_lines = [line for line in changed_lines if line is not None]
        label_path.write_text(
            "\n".join(remaining_lines) + ("\n" if remaining_lines else ""),
            encoding="utf-8",
        )

    return fixes
