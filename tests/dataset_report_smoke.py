"""独立统计验收，验证正常划分、全排除和故意构造的泄漏。"""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from annotation_import_smoke import snapshot

ROOT = Path(__file__).resolve().parents[1]


def main():
    source_dir = ROOT / 'outputs/browser_annotation_import_g64by_pq'
    source = source_dir / 'meme_index_annotated.csv'
    splits = ROOT / 'outputs/template_split_smoke_8yfstjk0'
    protected = [ROOT / 'data', source_dir, splits, ROOT / 'outputs/review_smoke_nefqxagt']
    before = [snapshot(p) for p in protected]
    output = Path(tempfile.mkdtemp(prefix='dataset_report_smoke_', dir=ROOT / 'outputs'))
    logs = []
    def run(split_dir, destination, expected=0):
        result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/dataset_report.py'),
                                 '--input', str(source), '--splits-dir', str(split_dir), '--output-dir', str(destination)],
                                capture_output=True, encoding='utf-8')
        logs.append(result.stdout + result.stderr)
        assert result.returncode == expected, result.stderr
    run(splits / 'explicit_include', output / 'include_report')
    report = json.loads((output / 'include_report/dataset_report.json').read_text(encoding='utf-8'))
    assert report['checks']['passed'] and not report['checks']['template_leakage']
    assert report['source']['samples'] == 5 and report['source']['templates'] == 3
    assert report['source']['uncertain'] == 5
    assert [report['partitions'][name]['samples'] for name in ('train', 'val', 'test')] == [1, 3, 1]
    saved = snapshot(output / 'include_report')
    run(splits / 'explicit_include', output / 'include_report', expected=1)
    assert snapshot(output / 'include_report') == saved
    run(splits / 'default_exclude', output / 'exclude_report')
    excluded = json.loads((output / 'exclude_report/dataset_report.json').read_text(encoding='utf-8'))
    assert excluded['assigned']['samples'] == 0 and excluded['partitions']['excluded_uncertain']['samples'] == 5
    bad = output / 'intentional_leakage'
    shutil.copytree(splits / 'explicit_include', bad)
    def read(path):
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            return reader.fieldnames, list(reader)
    fields, val_rows = read(bad / 'val.csv')
    _, train_rows = read(bad / 'train.csv')
    train_rows.append(val_rows.pop())
    for name, rows in [('train', train_rows), ('val', val_rows)]:
        with (bad / f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    run(bad, output / 'leakage_report', expected=2)
    leakage = json.loads((output / 'leakage_report/dataset_report.json').read_text(encoding='utf-8'))
    assert leakage['checks']['template_leakage']
    assert leakage['checks']['template_overlaps']['train/val'] == ['T0001']
    assert not leakage['checks']['duplicate_samples']
    assert before == [snapshot(p) for p in protected]
    summary = {'passed': True, 'samples': 5, 'templates': 3, 'uncertain': 5,
               'normal_split_no_leakage': True, 'all_excluded_report_valid': True,
               'intentional_leakage_detected': ['T0001'], 'existing_report_not_overwritten': True,
               'source_indices_images_and_formal_data_unchanged': True}
    (output / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'pipeline.log').write_text('\n'.join(logs), encoding='utf-8')
    print(output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
