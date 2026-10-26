"""校验二次人工复核导出，保留助手原标签与独立人工字段。"""
import csv
import json
from pathlib import Path

from memesense.data.annotation_import import validate_annotations
from memesense.data.review_import import valid_id

ORIGIN = 'assistant_visual_trial_not_human_gold'
EXPORT_FIELDS = ['sample_id', 'template_id', 'image_path', 'priority', 'annotation_origin',
                 'label_schema_version', 'human_label', 'human_note', 'human_review_status',
                 'assistant_reference_viewed', 'msairs_reference_viewed', 'reviewer_id']
HUMAN_FIELDS = [key for key in EXPORT_FIELDS if key not in
                {'sample_id', 'template_id', 'image_path', 'label_schema_version'}]


def validate_second_review(source: Path, baseline: Path, queue_path: Path, config: dict,
                           require_complete: bool = True) -> tuple[list[str], list[dict], dict]:
    """核对完整样本集合、来源和人工字段；不推断或替换任何标签。"""
    base_fields, originals, _ = validate_annotations(baseline, baseline, config)
    if set(base_fields) & set(HUMAN_FIELDS):
        raise ValueError('来源已含二次复核字段，请使用原助手已标注索引')
    base = {r['sample_id']: r for r in originals}
    queue = json.loads(queue_path.read_text(encoding='utf-8'))
    if not isinstance(queue, list) or not queue:
        raise ValueError('复核清单必须是非空数组')
    expected = {}
    for row in queue:
        if not isinstance(row, dict) or not isinstance(row.get('sample_id'), str):
            raise ValueError('复核清单样本结构无效')
        sid = row['sample_id']
        if sid in expected or sid not in base or not valid_id(sid, 'M'):
            raise ValueError('复核清单编号重复、无效或不在来源中')
        if row.get('priority') not in ('P0', 'P1', 'P2') or row.get('annotation_origin') != ORIGIN:
            raise ValueError('复核清单优先级或试标来源无效')
        for key, original_key in [('template_id','template_id'), ('image_path','image_path'),
                                  ('current_label','intent_label'), ('assistant_note','annotation_notes')]:
            if row.get(key) != base[sid][original_key]:
                raise ValueError(f'{sid} 复核清单与助手索引不一致：{key}')
        expected[sid] = row
    if set(expected) != set(base):
        raise ValueError('复核清单遗漏来源样本')
    counts = {'reviewed': 0, 'pending': 0}
    seen = set()
    results = []
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or set(fields) != set(EXPORT_FIELDS):
            raise ValueError('二次复核 CSV 表头缺失、重复或含未知字段')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'第 {reader.line_num} 行字段数量不一致')
            sid = row['sample_id']
            if not valid_id(sid, 'M') or sid in seen or sid not in base:
                raise ValueError(f'sample_id 无效、重复或未知：{sid}')
            seen.add(sid)
            for key in ('template_id', 'image_path', 'priority', 'annotation_origin'):
                if row[key] != expected[sid][key]:
                    raise ValueError(f'{sid} 来源字段被修改：{key}')
            if row['label_schema_version'] != config['version']:
                raise ValueError(f'{sid} 标签版本不匹配')
            label, status = row['human_label'], row['human_review_status']
            if label and label not in config['labels']:
                raise ValueError(f'{sid} 人工标签无效')
            if status not in counts or (status == 'reviewed') != bool(label):
                raise ValueError(f'{sid} 人工复核状态与标签不一致')
            for flag in ('assistant_reference_viewed', 'msairs_reference_viewed'):
                if row[flag] not in ('true', 'false'):
                    raise ValueError(f'{sid} 参考查看记录必须为 true/false')
            counts[status] += 1
            results.append({**base[sid], **{key: row[key] for key in HUMAN_FIELDS}})
    if seen != set(base):
        raise ValueError('二次复核 CSV 遗漏来源样本')
    if require_complete and counts['pending']:
        raise ValueError('尚有未完成人工复核的样本；可用 --check-only 仅校验')
    return base_fields + HUMAN_FIELDS, results, counts
