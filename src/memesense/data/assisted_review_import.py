"""校验助手预标审核批次，分别保存旧基线、新预标和人工结果。"""
import csv
from pathlib import Path

EDITABLE = {'human_label', 'human_note', 'human_review_status',
            'msairs_reference_viewed', 'reviewer_id'}


def read_rows(path: Path) -> list[dict[str, str]]:
    """严格读取CSV，拒绝重复编号、列名和错误行宽。"""
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or 'sample_id' not in fields:
            raise ValueError('CSV列名缺失或重复')
        rows = list(reader)
    if not rows or any(None in r or None in r.values() for r in rows):
        raise ValueError('CSV为空或行宽不正确')
    if len(rows) != len({r['sample_id'] for r in rows}):
        raise ValueError('sample_id重复')
    return rows


def validate(source: Path, expected: list[dict[str, str]], baseline: list[dict[str, str]],
             labels: set[str], complete: bool = True) -> tuple[list[dict[str, str]], dict]:
    """按固定批次核对不可变字段，未完成仅允许检查。"""
    rows = read_rows(source)
    exp = {r['sample_id']: r for r in expected}
    base = {r['sample_id']: r for r in baseline}
    if len(exp) != len(expected) or len(base) != len(baseline):
        raise ValueError('参考数据编号重复')
    if {r['sample_id'] for r in rows} != set(exp) or not set(exp) <= set(base):
        raise ValueError('批次样本缺失、多余或不在原始基线中')
    result = []
    counts = {'reviewed': 0, 'pending': 0, 'changed_labels': 0, 'msairs_viewed': 0}
    for row in rows:
        sid = row['sample_id']
        if set(row) != set(exp[sid]):
            raise ValueError(f'{sid} 列缺失或包含未知字段')
        for key, value in exp[sid].items():
            if key not in EDITABLE and row[key] != value:
                raise ValueError(f'{sid} 来源或预标字段被修改：{key}')
        for key in ('image_path', 'template_id'):
            if row[key] != base[sid][key]:
                raise ValueError(f'{sid} 与原始基线不符：{key}')
        label = row['human_label']
        if label and label not in labels:
            raise ValueError(f'{sid} 人工标签无效')
        status = 'reviewed' if label and row['human_note'].strip() else 'pending'
        if row['human_review_status'] != status:
            raise ValueError(f'{sid} 状态与标签、依据不一致')
        if not row['reviewer_id'].strip():
            raise ValueError(f'{sid} 缺少实际审核者')
        if row['msairs_reference_viewed'] not in ('true', 'false'):
            raise ValueError(f'{sid} MSAIRS查看记录无效')
        counts[status] += 1
        counts['changed_labels'] += int(bool(label) and label != row['assistant_prelabel'])
        counts['msairs_viewed'] += int(row['msairs_reference_viewed'] == 'true')
        result.append({**{'baseline_' + k: v for k, v in base[sid].items()}, **row,
                       'effective_label_source': 'human_review_of_assistant_prelabels',
                       'import_status': 'review_record_only_not_training_index'})
    if complete and counts['pending']:
        raise ValueError('尚有未完成审核；请使用 --check-only 检查备份')
    return result, counts
