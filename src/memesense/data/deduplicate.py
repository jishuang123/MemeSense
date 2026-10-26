"""完全重复检测：记录散列，不移动或删除原始图片。"""

import hashlib
import logging
import re
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
LOGGER = logging.getLogger(__name__)


def group_by_phash(
    rows: list[dict[str, str]], threshold: int = 6,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """按汉明距离的连通分量生成候选模板和直接匹配对，不改变输入。"""
    if not 0 <= threshold <= 64:
        raise ValueError("pHash 阈值必须在 0 到 64 之间")
    result = [row.copy() for row in rows]
    valid: list[tuple[int, int]] = []
    for index, row in enumerate(result):
        # 输出是重新计算的候选，不把旧人工模板当成相似性证据。
        row["template_id"] = ""
        value = row["phash"].strip()
        if not re.fullmatch(r"[0-9a-fA-F]{16}", value):
            LOGGER.warning("跳过 %s：pHash 为空或不是 64 位十六进制值", row["sample_id"])
            continue
        valid.append((index, int(value, 16)))
    valid.sort(key=lambda item: int(result[item[0]]["sample_id"][1:]))
    parents = list(range(len(result)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    pairs: list[dict[str, str]] = []
    for position, (left, left_hash) in enumerate(valid):
        for right, right_hash in valid[position + 1:]:
            distance = (left_hash ^ right_hash).bit_count()
            if distance <= threshold:
                parents[find(right)] = find(left)
                pairs.append({"sample_id_a": result[left]["sample_id"],
                              "image_path_a": result[left]["image_path"],
                              "sample_id_b": result[right]["sample_id"],
                              "image_path_b": result[right]["image_path"],
                              "distance": str(distance)})
        if (position + 1) % 100 == 0:
            LOGGER.info("已比较 %d/%d 个有效 pHash", position + 1, len(valid))

    groups: dict[int, list[int]] = {}
    for index, _ in valid:
        groups.setdefault(find(index), []).append(index)
    for members in groups.values():
        minimum = min(int(result[i]["sample_id"][1:]) for i in members)
        for index in members:
            result[index]["template_id"] = f"T{minimum:04d}"
    templates = {row["sample_id"]: row["template_id"] for row in result}
    for pair in pairs:
        pair["template_id"] = templates[pair["sample_id_a"]]
    LOGGER.info("候选模板 %d 个，其中多图片模板 %d 个；直接匹配对 %d 对",
                len(groups), sum(len(group) > 1 for group in groups.values()), len(pairs))
    return result, pairs


def sha256_file(path: Path) -> str:
    """以分块方式计算文件散列。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_images(root: Path) -> list[dict[str, str]]:
    """按文件名确定顺序；image_path 相对于原图目录。"""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("原图路径必须是目录")
    records = []
    canonical: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"图片路径越出原图目录：{path.name}")
        relative = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        first = canonical.setdefault(digest, relative)
        records.append({"image_path": relative, "sha256": digest,
                        "duplicate_of": "" if first == relative else first})
    return records
