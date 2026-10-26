"""使用原有独立标注数据验收模板划分，不更改其 uncertain 标签。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from annotation_import_smoke import snapshot

import csv

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    previous = ROOT / 'outputs/browser_annotation_import_g64by_pq'
    source = previous / 'meme_index_annotated.csv'
    protected = [ROOT / 'data', previous, ROOT / 'outputs/review_smoke_nefqxagt']
    before = [snapshot(path) for path in protected]
    output = Path(tempfile.mkdtemp(prefix='template_split_smoke_', dir=ROOT / 'outputs'))
    logs = []
    def run(target, policy='exclude', input_path=source, expected=0):
        result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/split_dataset.py'),
                                 '--input', str(input_path), '--output-dir', str(target), '--uncertain', policy],
                                capture_output=True, encoding='utf-8')
        logs.append(result.stdout + result.stderr)
        assert result.returncode == expected, result.stderr
    excluded_dir = output / 'default_exclude'
    run(excluded_dir)
    assert len(read(excluded_dir / 'excluded_uncertain.csv')) == 5
    assert all(not read(excluded_dir / f'{name}.csv') for name in ('train', 'val', 'test'))
    exclusion = json.loads((excluded_dir / 'split_report.json').read_text(encoding='utf-8'))
    assert not exclusion['has_eligible_samples'] and exclusion['warnings']
    included_dir = output / 'explicit_include'
    run(included_dir, 'include')
    parts = {name: read(included_dir / f'{name}.csv') for name in ('train', 'val', 'test')}
    groups = [{row['template_id'] for row in part} for part in parts.values()]
    assert all(len(group) == 1 for group in groups)
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    original = {row['sample_id']: row for row in read(source)}
    flattened = [row for part in parts.values() for row in part]
    assert len(flattened) == 5 and {row['sample_id']: row for row in flattened} == original
    repeated = output / 'same_seed'
    run(repeated, 'include')
    for name in ('train', 'val', 'test', 'excluded_uncertain'):
        assert (repeated / f'{name}.csv').read_bytes() == (included_dir / f'{name}.csv').read_bytes()
    saved = snapshot(included_dir)
    run(included_dir, 'include', expected=1)
    assert snapshot(included_dir) == saved
    # 空模板编号应在创建输出目录前失败。
    bad = output / 'invalid_template.csv'
    bad_rows = read(source)
    bad_rows[0]['template_id'] = ''
    with bad.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(bad_rows[0]))
        writer.writeheader(); writer.writerows(bad_rows)
    run(output / 'must_not_exist', input_path=bad, expected=1)
    assert not (output / 'must_not_exist').exists()
    assert before == [snapshot(path) for path in protected]
    report = {'passed': True, 'samples': 5, 'templates': 3,
              'default_exclude': {'excluded': 5, 'eligible': 0},
              'explicit_include': {name: len(part) for name, part in parts.items()},
              'template_leakage': False, 'same_seed_identical': True,
              'existing_output_protected': True, 'invalid_template_rejected': True,
              'original_indices_images_and_formal_data_unchanged': True,
              'note': 'include 仅验证分组流程；全部为 uncertain，不代表可用的意图分类训练数据。'}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'pipeline.log').write_text('\n'.join(logs), encoding='utf-8')
    print(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
