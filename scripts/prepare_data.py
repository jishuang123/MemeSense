"""只读扫描原图，增量维护带 pHash 的 CSV 图片索引。"""

import argparse
import csv
import logging
import re
import tempfile
from pathlib import Path

import imagehash
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
FIELDS = ["sample_id", "original_filename", "image_path", "width", "height",
          "file_size", "phash", "template_id", "ocr_text", "source"]


def find_images(input_dir: Path) -> list[Path]:
    """递归查找支持的文件，排序保证首次编号可复现。"""
    if not input_dir.is_dir():
        raise ValueError(f"输入目录不存在或不是目录：{input_dir}")
    return sorted((p for p in input_dir.rglob("*")
                   if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                  key=lambda p: p.relative_to(input_dir).as_posix())


def load_existing_index(output_path: Path) -> list[dict[str, str]]:
    """校验旧索引，损坏时停止，防止静默重编号。"""
    if not output_path.exists():
        return []
    with output_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError("已有索引缺少必要字段，请检查 CSV 表头")
        rows = list(reader)
    ids: set[int] = set()
    paths: set[str] = set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("已有索引包含字段数量不一致的行")
        sample_id, path = row["sample_id"], row["image_path"]
        if not re.fullmatch(r"M[0-9]{4,}", sample_id) or int(sample_id[1:]) < 1:
            raise ValueError(f"已有 sample_id 无效：{sample_id!r}")
        number = int(sample_id[1:])
        if number in ids or path in paths:
            raise ValueError("已有索引存在重复编号或重复图片路径")
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError(f"已有图片路径不是安全的相对路径：{path!r}")
        ids.add(number)
        paths.add(path)
    return rows


def calculate_phash(image: Image.Image) -> str:
    """计算 64 位感知散列，返回 16 位十六进制字符串。"""
    return str(imagehash.phash(image, hash_size=8))


def get_image_metadata(image_path: Path, input_dir: Path) -> dict[str, str]:
    """只读解码并收集元数据；多帧图片使用第一帧。"""
    if not image_path.resolve().is_relative_to(input_dir.resolve()):
        raise ValueError("图片链接指向输入目录之外")
    with Image.open(image_path) as image:
        image.verify()
    with Image.open(image_path) as image:
        image.load()
        return {
            "original_filename": image_path.name,
            "image_path": image_path.relative_to(input_dir).as_posix(),
            "width": str(image.width), "height": str(image.height),
            "file_size": str(image_path.stat().st_size),
            "phash": calculate_phash(image),
        }


def build_index(input_dir: Path, existing: list[dict[str, str]]) -> list[dict[str, str]]:
    """按相对路径复用编号；新增文件从历史最大编号递增。"""
    rows = [row.copy() for row in existing]
    by_path = {row["image_path"]: row for row in rows}
    next_number = max((int(row["sample_id"][1:]) for row in rows), default=0) + 1
    images = find_images(input_dir)
    LOGGER.info("发现 %d 个候选图片，已有 %d 条记录", len(images), len(rows))
    valid = added = skipped = 0
    found_paths: set[str] = set()
    for number, path in enumerate(images, 1):
        relative = path.relative_to(input_dir).as_posix()
        found_paths.add(relative)
        try:
            metadata = get_image_metadata(path, input_dir)
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            LOGGER.warning("跳过无法读取的图片 %s：%s（若已入库则保留历史记录）", relative, exc)
            skipped += 1
            continue
        if relative in by_path:
            by_path[relative].update(metadata)
        else:
            row = {"sample_id": f"M{next_number:04d}", **metadata,
                   "template_id": "", "ocr_text": "", "source": "unknown"}
            rows.append(row)
            by_path[relative] = row
            next_number += 1
            added += 1
        valid += 1
        if number % 100 == 0:
            LOGGER.info("已处理 %d/%d 个文件", number, len(images))
    missing = len(set(by_path) - found_paths)
    if missing:
        LOGGER.warning("%d 条历史记录对应的文件未找到，保留记录和原编号", missing)
    LOGGER.info("扫描完成：有效 %d，新增 %d，跳过 %d，索引总计 %d",
                valid, added, skipped, len(rows))
    return rows


def save_index(output_path: Path, rows: list[dict[str, str]]) -> None:
    """临时文件写完后替换 CSV，避免写入失败损坏旧索引。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = FIELDS + sorted({key for row in rows for key in row} - set(FIELDS))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="",
                                         dir=output_path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(output_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    """命令行入口；默认路径以项目根目录为基准。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/raw/images", help="图片输入目录")
    parser.add_argument("--output", type=Path, default=ROOT / "data/interim/meme_index.csv", help="CSV 索引路径")
    args = parser.parse_args()
    input_dir, output_path = args.input.resolve(), args.output.resolve()
    try:
        if output_path.is_relative_to(input_dir) or output_path.is_relative_to((ROOT / "data/raw").resolve()):
            raise ValueError("输出不能位于输入目录或 data/raw/ 内")
        if output_path.suffix.lower() != ".csv":
            raise ValueError("输出文件必须使用 .csv 扩展名")
        existing = load_existing_index(output_path)
        rows = build_index(input_dir, existing)
        save_index(output_path, rows)
    except (OSError, ValueError, csv.Error) as exc:
        LOGGER.error("索引构建失败：%s", exc)
        raise SystemExit(1) from exc
    LOGGER.info("已保存索引：%s", output_path)


if __name__ == "__main__":
    main()
