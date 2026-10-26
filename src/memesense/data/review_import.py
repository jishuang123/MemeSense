"""校验人工复核 CSV，并与其来源候选索引对照。"""

import csv
from pathlib import Path
import re

INDEX_FIELDS = ["sample_id", "original_filename", "image_path", "width", "height",
                "file_size", "phash", "template_id", "ocr_text", "source"]
REVIEW_FIELDS = ["review_original_template_id", "review_status"]
STATUSES = {"pending", "correct", "suspected"}


def valid_id(value: str, prefix: str) -> bool:
    """编号采用规范形式，如 M0001、T0001、M10000；不接受零或额外前导零。"""
    if not re.fullmatch(prefix + r"[0-9]{4,}", value):
        return False
    number = int(value[1:])
    return number > 0 and value == f"{prefix}{number:04d}"


def read_index(path: Path, reviewed: bool = False) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """读取 CSV，保留记录结束行号并检查表头、行宽与重复样本。"""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames
        required = INDEX_FIELDS + (REVIEW_FIELDS if reviewed else [])
        if not fields or len(set(fields)) != len(fields) or "" in fields:
            raise ValueError(f"{path.name}：CSV 表头为空或存在重复/空列名")
        missing = set(required) - set(fields)
        if missing:
            raise ValueError(f"{path.name}：缺少字段 {', '.join(sorted(missing))}")
        result, errors = [], []
        seen: set[str] = set()
        paths: set[str] = set()
        for row in reader:
            line = reader.line_num
            if None in row or any(value is None for value in row.values()):
                errors.append(f"第 {line} 行字段数量与表头不符")
                continue
            sample_id = row["sample_id"]
            if not valid_id(sample_id, "M"):
                errors.append(f"第 {line} 行 sample_id 无效：{sample_id!r}")
            if sample_id in seen:
                errors.append(f"第 {line} 行 sample_id 重复：{sample_id}")
            seen.add(sample_id)
            image_path = row["image_path"]
            if not image_path or Path(image_path).is_absolute() or ".." in Path(image_path).parts:
                errors.append(f"第 {line} 行 image_path 必须是安全的相对路径")
            if image_path in paths:
                errors.append(f"第 {line} 行 image_path 重复：{image_path!r}")
            paths.add(image_path)
            result.append((line, row))
        if not result and not errors:
            errors.append("索引没有样本，不能作为复核输入")
        if errors:
            raise ValueError(f"{path.name}：\n" + "\n".join(errors))
    return fields, result


def validate_review(reviewed: Path, baseline: Path, require_complete: bool = True
                    ) -> tuple[list[str], list[dict[str, str]], dict[str, int]]:
    """只允许模板及复核状态变化；默认拒绝未决样本，不过滤或自动确认。"""
    fields, records = read_index(reviewed, reviewed=True)
    base_fields, base_records = read_index(baseline)
    originals = {row["sample_id"]: row for _, row in base_records}
    errors: list[str] = []
    if set(base_fields) - set(fields):
        errors.append("复核 CSV 遗漏了原候选索引的列")
    counts = {status: 0 for status in sorted(STATUSES)}
    seen = set()
    for line, row in records:
        sample_id = row["sample_id"]
        seen.add(sample_id)
        status, template = row["review_status"], row["template_id"]
        if status not in STATUSES:
            errors.append(f"第 {line} 行 {sample_id}：review_status 无效：{status!r}")
        else:
            counts[status] += 1
        if template and not valid_id(template, "T"):
            errors.append(f"第 {line} 行 {sample_id}：template_id 无效：{template!r}")
        if status == "correct" and not template:
            errors.append(f"第 {line} 行 {sample_id}：已确认样本的 template_id 不能为空")
        original_template = row["review_original_template_id"]
        if original_template and not valid_id(original_template, "T"):
            errors.append(f"第 {line} 行 {sample_id}：原模板编号无效：{original_template!r}")
        original = originals.get(sample_id)
        if original is None:
            errors.append(f"第 {line} 行 {sample_id}：不在原候选索引中")
            continue
        for field in base_fields:
            if field not in {"template_id", *REVIEW_FIELDS} and row.get(field) != original[field]:
                errors.append(f"第 {line} 行 {sample_id}：原字段 {field} 被修改")
        expected_template = original.get("review_original_template_id", original["template_id"])
        if original_template != expected_template:
            errors.append(f"第 {line} 行 {sample_id}：review_original_template_id 与来源不一致")
    missing = set(originals) - seen
    if missing:
        errors.append("复核 CSV 遗漏样本：" + ", ".join(sorted(missing)))
    if require_complete and (counts["pending"] or counts["suspected"]):
        errors.append(f"复核未完成：pending={counts['pending']}，suspected={counts['suspected']}；"
                      "请继续人工确认，或用 --check-only 仅校验")
    if errors:
        raise ValueError("\n".join(errors))
    return fields, [row for _, row in records], counts


def save_reviewed_index(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    """独占创建新 CSV，已有文件绝不覆盖；失败时移除本次未写完的文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 序列化在创建前完成；x 模式阻止同路径及硬链接覆盖。
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    stream = path.open("x", encoding="utf-8-sig", newline="")
    try:
        with stream:
            stream.write(buffer.getvalue())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
