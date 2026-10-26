"""校验二次人工复核 CSV，独立另存助手原字段及人工结果。"""
import argparse
import csv
import json
import logging
from pathlib import Path
import yaml

from _bootstrap import ROOT
from build_annotation_page import load_labels
from memesense.data.second_review_import import validate_second_review
from memesense.data.review_import import save_reviewed_index


def main() -> None:
    """检查模式允许未完成；实际导入必须全量复核且输出不存在。"""
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('input', 'baseline', 'queue', 'labels', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        output = args.output.resolve()
        if not args.check_only:
            if output.exists() or output in {p.resolve() for p in [args.input,args.baseline,args.queue,args.labels]}:
                raise ValueError('输出已存在或指向输入，拒绝覆盖')
            if output.suffix.lower() != '.csv' or output.is_relative_to((ROOT/'data/raw').resolve()):
                raise ValueError('输出必须是 data/raw 之外的新 CSV')
        fields, rows, counts = validate_second_review(args.input, args.baseline, args.queue,
                                                      load_labels(args.labels), not args.check_only)
        logging.info('校验通过：%d 条，reviewed=%d，pending=%d', len(rows), counts['reviewed'], counts['pending'])
        if not args.check_only:
            save_reviewed_index(output, fields, rows)
            logging.info('已保存独立人工复核索引：%s', output)
        else:
            logging.info('仅校验，未写文件；不代表复核已完成')
    except (OSError, ValueError, csv.Error, yaml.YAMLError) as exc:
        logging.error('二次复核导入失败：%s', exc)
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
