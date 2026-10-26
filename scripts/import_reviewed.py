"""校验浏览器导出的复核 CSV，另存全部确认后的独立索引。"""

import argparse
import csv
import logging
from pathlib import Path

from _bootstrap import ROOT
from memesense.data.review_import import save_reviewed_index, validate_review


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="浏览器下载的复核 CSV")
    parser.add_argument("--baseline", type=Path, default=ROOT / "data/interim/meme_index_with_templates.csv",
                        help="生成此次复核页时使用的候选索引")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/meme_index_reviewed.csv")
    parser.add_argument("--check-only", action="store_true", help="仅校验字段与来源，报告未决状态，不写入文件")
    args = parser.parse_args()
    source, baseline, output = (path.resolve() for path in (args.input, args.baseline, args.output))
    try:
        if not args.check_only:
            if output in {source, baseline} or output.is_relative_to((ROOT / "data/raw").resolve()):
                raise ValueError("输出不能覆盖输入、来源索引或位于 data/raw/ 内")
            if output.suffix.lower() != ".csv":
                raise ValueError("输出必须是 .csv 文件")
            if output.exists():
                raise ValueError(f"输出已存在，拒绝覆盖，请指定新路径：{output}")
        fields, rows, counts = validate_review(source, baseline, require_complete=not args.check_only)
        logging.info("校验通过：%d 条，correct=%d，pending=%d，suspected=%d",
                     len(rows), counts["correct"], counts["pending"], counts["suspected"])
        if args.check_only:
            logging.info("仅校验，未写入任何文件；校验通过不代表复核已完成")
        else:
            save_reviewed_index(output, fields, rows)
            logging.info("已生成独立的已复核索引：%s", output)
    except (OSError, ValueError, csv.Error) as exc:
        logging.error("复核导入失败：%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
