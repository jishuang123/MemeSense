"""显式采用人工标签，同时归档助手原判断，保留全部复核证据。"""
from pathlib import Path

from memesense.data.annotation_import import validate_annotations
from memesense.data.second_review_import import HUMAN_FIELDS, ORIGIN

ARCHIVE_FIELDS = ['assistant_intent_label', 'assistant_annotation_notes',
                  'assistant_annotation_status', 'assistant_label_schema_version',
                  'effective_label_source']


def adopt_human_labels(source: Path, baseline: Path, config: dict) -> tuple[list[str], list[dict]]:
    """只转换完整、有效且与助手来源一致的人工索引；重复转换拒绝。"""
    fields, rows, _ = validate_annotations(source, baseline, config)
    base_fields, originals, _ = validate_annotations(baseline, baseline, config)
    if set(fields) & set(ARCHIVE_FIELDS) or set(base_fields) & set(HUMAN_FIELDS):
        raise ValueError('已转换或来源包含人工字段，拒绝重复转换')
    if not set(HUMAN_FIELDS).issubset(fields):
        raise ValueError('输入缺少人工二次复核字段')
    base = {r['sample_id']: r for r in originals}
    result = []
    for row in rows:
        sid = row['sample_id']
        for key in base_fields:
            if row[key] != base[sid][key]:
                raise ValueError(f'{sid} 助手原字段被修改：{key}')
        if row['annotation_origin'] != ORIGIN or row['priority'] not in ('P0','P1','P2'):
            raise ValueError(f'{sid} 复核来源或优先级无效')
        if row['human_review_status'] != 'reviewed' or row['human_label'] not in config['labels']:
            raise ValueError(f'{sid} 人工复核未完成或标签无效')
        if any(row[key] not in ('true','false') for key in ('assistant_reference_viewed','msairs_reference_viewed')):
            raise ValueError(f'{sid} 参考查看记录无效')
        result.append({**row,
            'assistant_intent_label': row['intent_label'],
            'assistant_annotation_notes': row['annotation_notes'],
            'assistant_annotation_status': row['annotation_status'],
            'assistant_label_schema_version': row['label_schema_version'],
            'effective_label_source': 'human_second_review',
            'intent_label': row['human_label'], 'annotation_notes': row['human_note'],
            'annotation_status': 'annotated'})
    return fields + ARCHIVE_FIELDS, result
