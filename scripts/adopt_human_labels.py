"""将独立人工复核索引转换成采用 human_label 的新标准已标注索引。"""
import argparse
import csv
import logging
from pathlib import Path
import yaml
from _bootstrap import ROOT
from build_annotation_page import load_labels
from memesense.data.adopt_human_labels import adopt_human_labels
from memesense.data.review_import import save_reviewed_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('input','baseline','labels','output'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        output = args.output.resolve()
        if output.exists() or output in {args.input.resolve(),args.baseline.resolve(),args.labels.resolve()}:
            raise ValueError('输出已存在或指向输入，拒绝覆盖')
        if output.suffix.lower() != '.csv' or output.is_relative_to((ROOT/'data/raw').resolve()):
            raise ValueError('输出必须是 data/raw 之外的新 CSV')
        fields, rows = adopt_human_labels(args.input,args.baseline,load_labels(args.labels))
        save_reviewed_index(output,fields,rows)
        logging.info('转换完成：%d 条，已采用人工标签，保留助手试标来源：%s',len(rows),output)
    except (OSError,ValueError,csv.Error,yaml.YAMLError) as exc:
        logging.error('转换失败：%s',exc)
        raise SystemExit(1) from exc


if __name__=='__main__':main()
