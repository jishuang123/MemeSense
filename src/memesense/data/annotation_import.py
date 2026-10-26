"""意图标注 CSV 校验：保持来源样本和原字段不变。"""

from pathlib import Path

from memesense.data.review_import import read_index, valid_id

ANNOTATION_FIELDS = ['intent_label', 'annotation_notes', 'annotation_status', 'label_schema_version']


def validate_annotations(annotated: Path, baseline: Path, config: dict,
                         require_complete: bool = True
                         ) -> tuple[list[str], list[dict[str, str]], dict[str, int]]:
    """校验导出结构、标签、状态、版本和来源；不补标签或自动转换版本。"""
    fields, records = read_index(annotated, reviewed=True)
    missing_fields = set(ANNOTATION_FIELDS) - set(fields)
    if missing_fields:
        raise ValueError('标注 CSV 缺少字段：' + ', '.join(sorted(missing_fields)))
    base_fields, base_records = read_index(baseline, reviewed=True)
    originals = {row['sample_id']: row for _, row in base_records}
    errors: list[str] = []
    if set(base_fields) - set(fields):
        errors.append('标注 CSV 遗漏了来源索引的列')
    for line, row in base_records:
        if row['review_status'] != 'correct' or not valid_id(row['template_id'], 'T'):
            errors.append(f'来源索引第 {line} 行 {row["sample_id"]} 尚未完成模板复核')
    counts = {'annotated': 0, 'pending': 0}
    seen: set[str] = set()
    for line, row in records:
        sample_id = row['sample_id']
        seen.add(sample_id)
        prefix = f'第 {line} 行 {sample_id}：'
        label, status = row['intent_label'], row['annotation_status']
        if label and label not in config['labels']:
            errors.append(prefix + f'意图标签不在当前配置中：{label!r}')
        if status not in counts:
            errors.append(prefix + f'annotation_status 无效：{status!r}')
        else:
            counts[status] += 1
            if (status == 'annotated') != bool(label):
                errors.append(prefix + '标注状态与意图标签不一致')
        if row['label_schema_version'] != config['version']:
            errors.append(prefix + f'标签版本必须为 {config["version"]!r}，实际为 {row["label_schema_version"]!r}')
        original = originals.get(sample_id)
        if original is None:
            errors.append(prefix + 'sample_id 不在来源已复核索引中')
            continue
        for field in base_fields:
            if field not in ANNOTATION_FIELDS and row.get(field) != original[field]:
                errors.append(prefix + f'原字段 {field} 被修改')
    missing_samples = set(originals) - seen
    if missing_samples:
        errors.append('标注 CSV 遗漏样本：' + ', '.join(sorted(missing_samples)))
    if require_complete and counts['pending']:
        errors.append(f'仍有 {counts["pending"]} 条未标注；请继续填写，或用 --check-only 仅校验')
    if errors:
        raise ValueError('\n'.join(errors))
    return fields, [row for _, row in records], counts
