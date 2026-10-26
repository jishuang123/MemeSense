"""在真实浏览器中完成旧测试标注，下载后校验及导入；仅写 outputs。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright, expect
from browser_review_smoke import ROOT, read_csv, snapshot


def main() -> None:
    prior = ROOT / 'outputs/annotation_smoke_kh0kneof'
    reviewed = ROOT / 'outputs/review_import_smoke_8yaeef1_'
    fixture_run = ROOT / 'outputs/review_smoke_nefqxagt'
    source = prior / json.loads((prior / 'report.json').read_text(encoding='utf-8'))['export']
    baseline = reviewed / 'meme_index_reviewed.csv'
    fixtures = fixture_run / 'fixtures'
    original_rows = read_csv(source)
    assert len(original_rows) == 5
    assert sum(row['annotation_status'] == 'pending' for row in original_rows) == 4
    protected = [ROOT / 'data', prior, reviewed, fixture_run]
    before = [snapshot(path) for path in protected]
    output = Path(tempfile.mkdtemp(prefix='browser_annotation_import_', dir=ROOT / 'outputs'))
    print(f'独立验收目录：{output}', flush=True)
    logs = []

    def run(script: str, *args: object, expected: int = 0) -> None:
        result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts' / script),
                                 *map(str, args)], capture_output=True, encoding='utf-8', cwd=ROOT)
        logs.append(result.stdout + result.stderr)
        assert result.returncode == expected, result.stderr

    page = output / 'annotation_in_progress.html'
    run('build_annotation_page.py', '--input', source, '--images', fixtures, '--output', page)
    rejected = output / 'must_not_exist.csv'
    run('import_annotations.py', '--input', source, '--baseline', baseline, '--output', rejected, expected=1)
    assert not rejected.exists()
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True, timeout=20000)
        context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1050})
        tab = context.new_page()
        tab.on('pageerror', lambda error: errors.append(str(error)))
        tab.goto(page.as_uri())
        expect(tab.locator('#progress')).to_contain_text('已填写 1 / 5')
        for image in tab.locator('img').all():
            image.scroll_into_view_if_needed()
            image.evaluate('(image) => image.decode()')
        for row in original_rows:
            if row['annotation_status'] == 'pending':
                sample_id = row['sample_id']
                tab.get_by_label(f'{sample_id} 意图', exact=True).select_option('uncertain')
                note = row['annotation_notes']
                note += ('\n' if note else '') + '独立测试复核：图片缺少对话语境，无法确定主要交流意图。'
                tab.get_by_label(f'{sample_id} 备注', exact=True).fill(note)
        expect(tab.locator('#progress')).to_contain_text('已填写 5 / 5')
        tab.screenshot(path=str(output / 'completed_in_browser.png'), full_page=True)
        tab.locator('#pending').check()
        expect(tab.locator('.card:visible')).to_have_count(0)
        with tab.expect_download() as info:
            tab.get_by_role('button', name='导出标注 CSV', exact=True).click()
        download = info.value
        exported = output / download.suggested_filename
        download.save_as(exported)
        assert download.failure() is None
        rows = read_csv(exported)
        assert len(rows) == 5
        for previous, row in zip(original_rows, rows):
            assert row['intent_label'] == 'uncertain' and row['annotation_status'] == 'annotated'
            assert row['annotation_notes'].strip()
            for key, value in previous.items():
                if key not in {'intent_label', 'annotation_status', 'annotation_notes'}:
                    assert row[key] == value, key
            if previous['annotation_status'] == 'annotated':
                assert row == previous
        exported_before = exported.read_bytes()
        accepted = output / 'meme_index_annotated.csv'
        run('import_annotations.py', '--input', exported, '--baseline', baseline,
            '--output', accepted, '--check-only')
        assert not accepted.exists()
        run('import_annotations.py', '--input', exported, '--baseline', baseline, '--output', accepted)
        assert read_csv(accepted) == rows
        accepted_before = accepted.read_bytes()
        run('import_annotations.py', '--input', exported, '--baseline', baseline,
            '--output', accepted, expected=1)
        assert accepted.read_bytes() == accepted_before
        assert exported.read_bytes() == exported_before
        final_page = output / 'annotation_completed.html'
        run('build_annotation_page.py', '--input', accepted, '--images', fixtures, '--output', final_page)
        tab.goto(final_page.as_uri())
        expect(tab.locator('#progress')).to_contain_text('已填写 5 / 5')
        for row in rows:
            expect(tab.get_by_label(f'{row["sample_id"]} 意图', exact=True)).to_have_value('uncertain')
            expect(tab.get_by_label(f'{row["sample_id"]} 备注', exact=True)).to_have_value(row['annotation_notes'])
        assert not errors, errors
        version = browser.version
        browser.close()
    assert before == [snapshot(path) for path in protected]
    report = {'passed': True, 'browser': f'Edge {version} headless', 'samples': 5,
              'completed_in_browser': 4, 'previous_annotation_preserved': True,
              'annotated': 5, 'pending': 0, 'intent_label': 'uncertain',
              'label_schema_version': rows[0]['label_schema_version'],
              'download': exported.name, 'accepted_index': accepted.name,
              'check_only_wrote_nothing': True, 'pending_import_rejected': True,
              'repeat_import_rejected': True, 'export_matches_import': True,
              'formal_data_and_previous_test_files_unchanged': True, 'browser_errors': errors}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'pipeline.log').write_text('\n'.join(logs), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(output)


if __name__ == '__main__':
    main()
