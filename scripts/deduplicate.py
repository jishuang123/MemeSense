"""读取图片索引，输出 pHash 候选模板索引和相似图片对供人工复核。"""

import argparse
import csv
import logging
import tempfile
from pathlib import Path

from _bootstrap import ROOT
from prepare_data import FIELDS, load_existing_index
from memesense.data.deduplicate import group_by_phash

LOGGER = logging.getLogger(__name__)
PAIR_FIELDS = ["template_id", "sample_id_a", "image_path_a", "sample_id_b", "image_path_b", "distance"]


def save_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    """写入临时 CSV 后替换目标，支持空表及额外人工列。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="",
                                         dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    """默认另存候选索引，拒绝覆盖输入或向原图目录写入。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/interim/meme_index.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/interim/meme_index_with_templates.csv")
    parser.add_argument("--pairs", type=Path, default=ROOT / "data/interim/near_duplicate_pairs.csv")
    parser.add_argument("--threshold", type=int, default=6, help="汉明距离上限，0–64，默认 6（待人工调优）")
    args = parser.parse_args()
    source, output, pairs_path = (p.resolve() for p in (args.input, args.output, args.pairs))
    try:
        if not source.is_file():
            raise ValueError(f"输入索引不存在：{source}，请先运行 prepare_data.py")
        if len({source, output, pairs_path}) != 3:
            raise ValueError("输入、候选索引和图片对 CSV 必须使用不同路径")
        for path in (output, pairs_path):
            if path.is_relative_to((ROOT / "data/raw").resolve()) or path.suffix.lower() != ".csv":
                raise ValueError("输出必须是 data/raw/ 之外的 CSV 文件")
        rows = load_existing_index(source)
        with source.open(encoding="utf-8-sig", newline="") as stream:
            fields = csv.DictReader(stream).fieldnames or FIELDS
        if any(row["template_id"] for row in rows):
            LOGGER.warning("输入已有 template_id：原索引保持不变，输出将重新计算候选编号")
        grouped, pairs = group_by_phash(rows, args.threshold)
        save_csv(output, grouped, fields)
        save_csv(pairs_path, pairs, PAIR_FIELDS)
    except (OSError, ValueError, csv.Error) as exc:
        LOGGER.error("近重复检测失败：%s", exc)
        raise SystemExit(1) from exc
    LOGGER.info("候选索引：%s", output)
    LOGGER.info("直接相似对：%s；阈值 %d，结果需要人工复核", pairs_path, args.threshold)


if __name__ == "__main__":
    main()
