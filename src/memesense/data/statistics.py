"""数据集统计及独立划分审计，不读取图片。"""

from collections import Counter
import csv
from itertools import combinations
from pathlib import Path


def read_partition(path: Path, required: list[str]) -> list[dict[str, str]]:
    """读取允许为空的划分 CSV，拒绝异常表头或行宽。"""
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames
        if not fields or len(set(fields)) != len(fields) or not set(required).issubset(fields):
            raise ValueError(f'{path.name}：表头重复或缺少来源字段')
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'{path.name} 第 {reader.line_num} 行字段数量异常')
            rows.append(row)
    return rows


def summarize(rows: list[dict[str, str]], labels: list[str]) -> dict:
    """统计记录数、唯一样本数、模板数和全部配置标签（包括零计数）。"""
    counts = Counter(row['intent_label'] for row in rows)
    return {'samples': len(rows), 'unique_samples': len({r['sample_id'] for r in rows}),
            'templates': len({r['template_id'] for r in rows}),
            'uncertain': counts['uncertain'],
            'labels': {label: counts[label] for label in sorted(set(labels) | set(counts))}}


def audit_dataset(source: list[dict[str, str]], partitions: dict[str, list[dict[str, str]]],
                  labels: list[str]) -> dict:
    """重新检查样本完整性、原字段及模板交叉，不信任已有报告中的结论。"""
    originals = {row['sample_id']: row for row in source}
    errors, warnings = [], []
    placements: dict[str, list[str]] = {}
    for name, rows in partitions.items():
        for row in rows:
            sample_id = row['sample_id']
            placements.setdefault(sample_id, []).append(name)
            if sample_id not in originals:
                errors.append(f'{name} 存在未知样本 {sample_id}')
            else:
                changed = [field for field, value in originals[sample_id].items() if row.get(field) != value]
                if changed:
                    errors.append(f'{name} 的 {sample_id} 原字段被修改：{", ".join(changed)}')
            if name == 'excluded_uncertain' and row['intent_label'] != 'uncertain':
                errors.append(f'排除清单含非 uncertain 样本 {sample_id}')
    duplicates = {sample: names for sample, names in placements.items() if len(names) > 1}
    missing = sorted(set(originals) - set(placements))
    if duplicates:
        errors.append('样本重复出现：' + ', '.join(sorted(duplicates)))
    if missing:
        errors.append('划分及排除清单遗漏样本：' + ', '.join(missing))
    overlaps = {}
    for left, right in combinations(('train', 'val', 'test'), 2):
        common = sorted({r['template_id'] for r in partitions[left]} & {r['template_id'] for r in partitions[right]})
        overlaps[f'{left}/{right}'] = common
        if common:
            errors.append(f'模板跨集合 {left}/{right}：{", ".join(common)}')
    assigned = [r for name in ('train', 'val', 'test') for r in partitions[name]]
    if not assigned:
        warnings.append('三个集合均为空，当前没有可用于训练评估的样本。')
    elif all(r['intent_label'] == 'uncertain' for r in assigned):
        warnings.append('划分内全部为“无法判断”，不能据此声称已具备明确意图分类数据。')
    for name in ('train', 'val', 'test'):
        if not partitions[name]:
            warnings.append(f'{name} 为空。')
        absent = set(r['intent_label'] for r in assigned) - set(r['intent_label'] for r in partitions[name])
        if absent:
            warnings.append(f'{name} 缺少已纳入数据的类别：{", ".join(sorted(absent))}')
    return {'source': summarize(source, labels), 'assigned': summarize(assigned, labels),
            'partitions': {name: summarize(rows, labels) for name, rows in partitions.items()},
            'checks': {'passed': not errors, 'template_leakage': any(overlaps.values()),
                       'template_overlaps': overlaps, 'duplicate_samples': duplicates, 'missing_samples': missing},
            'errors': errors, 'warnings': warnings}
