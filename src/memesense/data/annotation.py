"""JSONL 标注读写与单标签校验。"""

import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"第 {number} 行不是 JSON 对象")
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """独占创建，防止覆盖已有人工工作。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def validate_annotations(rows: list[dict], labels: list[str]) -> None:
    if not rows:
        raise ValueError("标注文件为空")
    seen: set[str] = set()
    group_labels: dict[str, str] = {}
    for index, row in enumerate(rows, 1):
        for key in ("image_path", "sha256", "text", "label"):
            if not isinstance(row.get(key), str):
                raise ValueError(f"第 {index} 行缺少字符串字段 {key}")
        path = Path(row["image_path"])
        if not row["image_path"] or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"第 {index} 行图片路径必须是安全的相对路径")
        if row["image_path"] in seen:
            raise ValueError(f"图片重复标注：{row['image_path']}")
        seen.add(row["image_path"])
        digest = row["sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"第 {index} 行 SHA-256 无效")
        if row["label"] not in labels:
            raise ValueError(f"第 {index} 行标签无效：{row['label']!r}")
        if group_labels.setdefault(digest, row["label"]) != row["label"]:
            raise ValueError("完全重复的图片存在冲突标签")
