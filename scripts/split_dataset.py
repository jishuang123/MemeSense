"""从已标注索引按 template_id 划分数据，仅创建新的 CSV 清单和报告。"""

import argparse
from collections import Counter
import csv
import hashlib
import json
import logging
from pathlib import Path

import yaml

from _bootstrap import ROOT
from build_annotation_page import load_labels
from memesense.data.annotation_import import ANNOTATION_FIELDS
from memesense.data.review_import import read_index, valid_id, save_reviewed_index
from memesense.data.split import split_by_template


def load_annotated(path: Path, config: dict) -> tuple[list[str], list[dict[str, str]]]:
    """检查已标注索引内部一致性，不用缺失字段推断标签或状态。"""
    fields, records = read_index(path, reviewed=True)
    missing = set(ANNOTATION_FIELDS) - set(fields)
    if missing:
        raise ValueError('缺少标注字段：' + ', '.join(sorted(missing)))
    errors = []
    for line, row in records:
        prefix = f'第 {line} 行 {row["sample_id"]}：'
        if row['review_status'] != 'correct' or not valid_id(row['template_id'], 'T'):
            errors.append(prefix + '模板复核状态或 template_id 无效')
        if row['annotation_status'] != 'annotated' or row['intent_label'] not in config['labels']:
            errors.append(prefix + '尚未完成标注或意图标签无效')
        if row['label_schema_version'] != config['version']:
            errors.append(prefix + '标签版本与配置不一致')
    if errors:
        raise ValueError('\n'.join(errors))
    return fields, [row for _, row in records]


def main() -> None:
    """输出目录必须不存在，防止覆盖已确定的数据划分。"""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/processed/meme_index_annotated.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/splits')
    parser.add_argument('--labels', type=Path, default=ROOT / 'configs/labels.yaml')
    parser.add_argument('--ratios', nargs=3, type=float, default=(0.8, 0.1, 0.1), metavar=('TRAIN', 'VAL', 'TEST'))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--uncertain', choices=['exclude', 'include'], default='exclude')
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output_dir.resolve()
    try:
        if output.exists():
            raise ValueError('输出目录已存在，请指定新的目录；不会覆盖旧划分')
        if output.is_relative_to((ROOT / 'data/raw').resolve()):
            raise ValueError('输出不能位于 data/raw/ 内')
        config = load_labels(args.labels)
        fields, rows = load_annotated(source, config)
        partitions, excluded = split_by_template(rows, tuple(args.ratios), args.seed, args.uncertain)
        warnings = []
        eligible_count = len(rows) - len(excluded)
        if not eligible_count:
            warnings.append('没有可划分样本：所有样本均被排除；输出仅供审计，不能作为训练评估数据。')
        sets = {name: {row['template_id'] for row in part} for name, part in partitions.items()}
        for i, name in enumerate(('train', 'val', 'test')):
            if args.ratios[i] > 0 and not partitions[name]:
                warnings.append(f'{name} 为空：有效模板组数不足。')
        for left, right in (('train', 'val'), ('train', 'test'), ('val', 'test')):
            if sets[left] & sets[right]:
                raise ValueError('内部错误：同一模板跨集合')
        included_labels = {row['intent_label'] for part in partitions.values() for row in part}
        for i, name in enumerate(('train', 'val', 'test')):
            missing_labels = included_labels - {row['intent_label'] for row in partitions[name]}
            if args.ratios[i] > 0 and missing_labels:
                warnings.append(f'{name} 缺少标签：{", ".join(sorted(missing_labels))}；当前不进行类别分层。')
        report = {
            'input': str(source), 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'label_schema_version': config['version'], 'seed': args.seed,
            'ratios': dict(zip(('train', 'val', 'test'), args.ratios)),
            'ratio_unit': 'template_groups', 'algorithm': 'shuffle_largest_remainder_min_one_v1',
            'uncertain_policy': args.uncertain, 'input_samples': len(rows),
            'eligible_samples': eligible_count, 'excluded_samples': len(excluded),
            'excluded_reason': 'intent_label=uncertain' if args.uncertain == 'exclude' else None,
            'has_eligible_samples': bool(eligible_count), 'template_leakage': False,
            'splits': {name: {'samples': len(part), 'templates': len(sets[name]),
                              'labels': dict(sorted(Counter(row['intent_label'] for row in part).items())),
                              'template_ids': sorted(sets[name])}
                       for name, part in partitions.items()}, 'warnings': warnings,
        }
        output.mkdir(parents=True, exist_ok=False)
        for name, part in partitions.items():
            save_reviewed_index(output / f'{name}.csv', fields, part)
            logging.info('%s：%d 样本，%d 模板', name, len(part), len(sets[name]))
        save_reviewed_index(output / 'excluded_uncertain.csv', fields, excluded)
        # 最后写报告；报告存在表示本次清单均已写完。
        with (output / 'split_report.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        for message in warnings:
            logging.warning(message)
        logging.info('划分完成：%s；排除 %d 条 uncertain', output, len(excluded))
    except (OSError, ValueError, csv.Error, yaml.YAMLError) as exc:
        logging.error('划分失败：%s', exc)
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
