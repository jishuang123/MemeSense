"""导入当前7批助手预标人工审核；输出独立目录，不改原数据。"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import yaml

from _bootstrap import ROOT
from memesense.data.assisted_review_import import read_rows, validate


def load_batch(batch: str) -> tuple[list[dict[str, str]], list[dict[str, str]], set[str], list[Path]]:
    """从已交付材料加载批次预期字段，不执行页面脚本。"""
    pilot = ROOT / 'outputs/msairs_pilot_20261016'
    base_path = pilot / 'intent_trial_v1/meme_index_annotated.csv'
    if batch == 'batch01':
        folder = ROOT / 'outputs/msairs_batch01_assisted_review_v1'
        queue_path = ROOT / 'outputs/msairs_human_review_batch01_v1/coordinator/review_queue.json'
        labels_path = ROOT / 'outputs/msairs_human_review_batch01_v1/coordinator/labels.yaml'
        pre_path = folder / 'assistant_prelabels_24.csv'
        origin = 'assistant_visual_trial_batch01_20261021'
    else:
        parent = ROOT / 'outputs/msairs_remaining_assisted_review_v1'
        folder = parent / batch
        queue_path, labels_path = folder / 'review_queue.json', parent / 'labels.yaml'
        pre_path = folder / 'assistant_prelabels.csv'
        origin = 'assistant_visual_trial_remaining_20261021'
    config = yaml.safe_load(labels_path.read_text(encoding='utf-8'))
    queue = json.loads(queue_path.read_text(encoding='utf-8'))
    pre = {r['sample_id']: r for r in read_rows(pre_path)}
    if {r['sample_id'] for r in queue} != set(pre) or len(queue) != len(pre):
        raise ValueError('批次预标与清单不匹配')
    expected = []
    for r in queue:
        p = pre[r['sample_id']]
        if p['label_schema_version'] != config['version'] or p['suggested_label'] not in config['labels']:
            raise ValueError('批次预标版本或标签无效')
        item = {k: r[k] for k in ('sample_id', 'template_id', 'image_path', 'priority', 'annotation_origin')}
        item.update(label_schema_version=config['version'], human_label='', human_note='',
                    human_review_status='pending', assistant_reference_viewed='true',
                    msairs_reference_viewed='false', reviewer_id='',
                    assistant_prelabel=p['suggested_label'], assistant_prelabel_reason=p['suggested_reason'],
                    review_mode='human_review_of_assistant_prelabels', prelabel_origin=origin,
                    rule_clarification_id='round2_boundary_clarification_20261020')
        if batch != 'batch01':
            item['review_batch_id'] = batch
        expected.append(item)
    return expected, read_rows(base_path), set(config['labels']), [queue_path, pre_path, labels_path, base_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--batch', choices=[f'batch{i:02d}' for i in range(1, 8)], required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        expected, base, labels, inputs = load_batch(args.batch)
        raw = args.input.read_bytes()
        rows, counts = validate(args.input, expected, base, labels, not args.check_only)
        print(json.dumps({'batch': args.batch, 'samples': len(rows), **counts}, ensure_ascii=False))
        if args.check_only:
            print('检查通过；未写入文件，不代表所有审核已完成。')
            return
        if args.output_dir is None:
            raise ValueError('实际导入需要 --output-dir 指定新目录')
        output = args.output_dir.resolve()
        if output.exists() or output.is_relative_to((ROOT / 'data/raw').resolve()) or output.is_relative_to((ROOT / 'outputs/msairs_pilot_20261016/images').resolve()):
            raise ValueError('输出目录已存在或位于原图目录内')
        output.mkdir(parents=True, exist_ok=False)
        with (output / 'reviewed_batch.csv').open('x', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with (output / 'original_export.csv').open('xb') as f:
            f.write(raw)
        audit = {'batch': args.batch, 'counts': counts, 'source': str(args.input.resolve()),
                 'source_sha256': hashlib.sha256(raw).hexdigest(),
                 'input_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                 'note': '人工审核助手预标；非独立盲标。baseline_*保留原助手标签及版本；未转换训练索引。'}
        with (output / 'import_audit.json').open('x', encoding='utf-8') as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        print(output)
    except (OSError, ValueError, KeyError, csv.Error, yaml.YAMLError) as exc:
        parser.exit(1, f'导入失败：{exc}\n')


if __name__ == '__main__':
    main()
