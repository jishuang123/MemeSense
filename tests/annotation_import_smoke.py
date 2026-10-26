"""使用已有独立数据验证标注导入；完成版是明确的合成验收数据。"""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def snapshot(path):
    return {str(p.relative_to(path)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in path.rglob('*') if p.is_file()}


def main():
    prior = ROOT / 'outputs/annotation_smoke_kh0kneof'
    baseline_dir = ROOT / 'outputs/review_import_smoke_8yaeef1_'
    fixtures = ROOT / 'outputs/review_smoke_nefqxagt/fixtures'
    source = prior / json.loads((prior / 'report.json').read_text(encoding='utf-8'))['export']
    baseline = baseline_dir / 'meme_index_reviewed.csv'
    protected = [ROOT / 'data', prior, baseline_dir, fixtures]
    before = [snapshot(path) for path in protected]
    output = Path(tempfile.mkdtemp(prefix='annotation_import_smoke_', dir=ROOT / 'outputs'))
    logs = []
    def run(input_path, target, check=False, expected=0):
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/import_annotations.py'),
                   '--input', str(input_path), '--baseline', str(baseline), '--output', str(target)]
        if check:
            command.append('--check-only')
        result = subprocess.run(command, capture_output=True, encoding='utf-8')
        logs.append(result.stdout + result.stderr)
        assert result.returncode == expected, result.stderr
    rejected = output / 'must_not_exist.csv'
    run(source, rejected, check=True)
    assert not rejected.exists()
    run(source, rejected, expected=1)
    assert not rejected.exists()
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    # 没有真实对话语境，不编造类别；只为测试成功导入路径创建副本。
    for row in rows:
        if not row['intent_label']:
            row.update(intent_label='uncertain', annotation_status='annotated',
                       annotation_notes=row['annotation_notes'] + '\n合成导入验收数据：无对话语境，无法判断。')
    complete = output / 'synthetic_completed_annotations.csv'
    with complete.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    accepted = output / 'meme_index_annotated.csv'
    run(complete, accepted, check=True)
    assert not accepted.exists()
    run(complete, accepted)
    with accepted.open(encoding='utf-8-sig', newline='') as stream:
        assert list(csv.DictReader(stream)) == rows
    saved = accepted.read_bytes()
    run(complete, accepted, expected=1)
    assert accepted.read_bytes() == saved
    assert before == [snapshot(path) for path in protected]
    report = {'passed': True, 'samples': len(rows), 'annotated': len(rows), 'pending': 0,
              'label': 'uncertain', 'version': rows[0]['label_schema_version'],
              'synthetic_completion_only': True, 'previous_download_unchanged': True,
              'formal_data_and_original_images_unchanged': True,
              'pending_import_rejected': True, 'check_only_wrote_nothing': True,
              'repeat_import_rejected': True, 'accepted_index': accepted.name}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'pipeline.log').write_text('\n'.join(logs), encoding='utf-8')
    print(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
