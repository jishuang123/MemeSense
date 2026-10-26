"""校验意图标注 CSV，生成独立已标注索引，不覆盖已有文件。"""

import argparse
import csv
import logging
from pathlib import Path

import yaml

from _bootstrap import ROOT
from build_annotation_page import load_labels
from memesense.data.annotation_import import validate_annotations
from memesense.data.review_import import save_reviewed_index


def main() -> None:
    """默认只接受全部填写的结果；--check-only 允许合法的未完成标注。"""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='浏览器导出的意图标注 CSV')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'data/processed/meme_index_reviewed.csv')
    parser.add_argument('--labels', type=Path, default=ROOT / 'configs/labels.yaml')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/processed/meme_index_annotated.csv')
    parser.add_argument('--check-only', action='store_true', help='仅校验，不写入；允许 pending 样本')
    args = parser.parse_args()
    source, baseline, labels, output = (p.resolve() for p in (args.input, args.baseline, args.labels, args.output))
    try:
        if not args.check_only:
            if output in {source, baseline, labels} or output.is_relative_to((ROOT / 'data/raw').resolve()):
                raise ValueError('输出不能覆盖输入、来源、标签配置或位于 data/raw/ 内')
            if output.suffix.lower() != '.csv':
                raise ValueError('输出必须是 .csv 文件')
            if output.exists():
                raise ValueError(f'输出已存在，拒绝覆盖：{output}')
        config = load_labels(labels)
        fields, rows, counts = validate_annotations(source, baseline, config, not args.check_only)
        logging.info('校验通过：%d 条，annotated=%d，pending=%d，标签版本=%s',
                     len(rows), counts['annotated'], counts['pending'], config['version'])
        if args.check_only:
            logging.info('仅校验，未写入任何文件；通过不代表全部填写或标签质量已审核')
        else:
            save_reviewed_index(output, fields, rows)
            logging.info('已生成独立的已标注索引：%s', output)
    except (OSError, ValueError, csv.Error, yaml.YAMLError) as exc:
        logging.error('意图标注导入失败：%s', exc)
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
