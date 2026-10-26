"""继续独立测试数据的浏览器复核，验证下载、校验和安全导入。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright, expect

from browser_review_smoke import ROOT, read_csv, snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-run', type=Path, required=True,
                        help='先前 browser_review_smoke 生成的独立测试目录')
    args = parser.parse_args()
    previous = args.fixture_run.resolve()
    if not previous.is_relative_to((ROOT / 'outputs').resolve()):
        raise ValueError('只允许使用 outputs 内的测试目录')
    previous_report = json.loads((previous / 'report.json').read_text(encoding='utf-8'))
    source = (previous / previous_report['export']).resolve()
    assert source.is_relative_to(previous)
    baseline = previous / 'grouped.csv'
    fixtures = previous / 'fixtures'
    rows = read_csv(source)
    assert {r['sample_id'] for r in rows} == {f'M{i:04d}' for i in range(1, 6)}
    by_id = {r['sample_id']: r for r in rows}
    assert (fixtures / by_id['M0001']['image_path']).read_bytes() == (fixtures / by_id['M0002']['image_path']).read_bytes()
    formal_before, previous_before = snapshot(ROOT / 'data'), snapshot(previous)
    output = Path(tempfile.mkdtemp(prefix='review_import_smoke_', dir=ROOT / 'outputs'))
    print(f'验收目录：{output}', flush=True)
    logs = []

    def run(script: str, *arguments: object, expected: int = 0) -> None:
        result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts' / script),
                                 *map(str, arguments)], cwd=ROOT, capture_output=True, encoding='utf-8')
        logs.append(result.stdout + result.stderr)
        assert result.returncode == expected, result.stderr

    page = output / 'review_in_progress.html'
    run('build_review_page.py', '--input', source, '--images', fixtures, '--output', page)
    # 先证实旧下载中的未决样本不能导入。
    rejected = output / 'must_not_exist.csv'
    run('import_reviewed.py', '--input', source, '--baseline', baseline,
        '--output', rejected, expected=1)
    assert not rejected.exists()
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True, timeout=20000)
        context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1050})
        tab = context.new_page()
        tab.on('pageerror', lambda error: errors.append(str(error)))
        tab.goto(page.as_uri())
        expect(tab.locator('.card')).to_have_count(5)
        for image in tab.locator('.preview img').all():
            image.scroll_into_view_if_needed()
            image.evaluate('(image) => image.decode()')
        tab.screenshot(path=str(output / 'before_review.png'), full_page=True)
        tab.get_by_role('textbox', name='M0002 的候选 template_id', exact=True).fill('T0001')
        for group in tab.locator('.group').all():
            group.get_by_role('button', name='分组正确', exact=True).click()
            expect(group.locator('.group-status')).to_have_text('分组正确')
        assert tab.locator('.sample-status').all_text_contents() == ['分组正确'] * 5
        with tab.expect_download() as download_info:
            tab.get_by_role('button', name='导出复核 CSV', exact=True).click()
        download = download_info.value
        downloaded = output / download.suggested_filename
        download.save_as(downloaded)
        assert download.failure() is None
        tab.screenshot(path=str(output / 'after_review.png'), full_page=True)
        reviewed = read_csv(downloaded)
        assert len(reviewed) == 5 and all(r['review_status'] == 'correct' for r in reviewed)
        assert [r['template_id'] for r in reviewed] == ['T0001', 'T0001', 'T0001', 'T0004', 'T0005']
        downloaded_before = downloaded.read_bytes()
        accepted = output / 'meme_index_reviewed.csv'
        run('import_reviewed.py', '--input', downloaded, '--baseline', baseline,
            '--output', accepted, '--check-only')
        assert not accepted.exists()
        run('import_reviewed.py', '--input', downloaded, '--baseline', baseline, '--output', accepted)
        assert read_csv(accepted) == reviewed
        accepted_before = accepted.read_bytes()
        # 已存在的输出不能被第二次导入覆盖。
        run('import_reviewed.py', '--input', downloaded, '--baseline', baseline,
            '--output', accepted, expected=1)
        assert accepted.read_bytes() == accepted_before
        assert downloaded.read_bytes() == downloaded_before
        final_page = output / 'review_completed.html'
        run('build_review_page.py', '--input', accepted, '--images', fixtures, '--output', final_page)
        tab.goto(final_page.as_uri())
        expect(tab.locator('.group')).to_have_count(3)
        assert tab.locator('.sample-status').all_text_contents() == ['分组正确'] * 5
        for image in tab.locator('.preview img').all():
            image.scroll_into_view_if_needed()
            image.evaluate('(image) => image.decode()')
        tab.screenshot(path=str(output / 'completed.png'), full_page=True)
        assert not errors, errors
        version = browser.version
        browser.close()
    assert previous_before == snapshot(previous), '旧测试图片或索引被修改'
    assert formal_before == snapshot(ROOT / 'data'), '正式数据目录被修改'
    report = {'passed': True, 'browser': f'Microsoft Edge {version} (headless)',
              'source_test_run': str(previous), 'samples': 5, 'templates': 3,
              'review_status': {'correct': 5, 'pending': 0, 'suspected': 0},
              'correction': 'M0002: T0099 -> T0001 (identical file to M0001)',
              'download': downloaded.name, 'accepted_index': accepted.name,
              'unresolved_import_rejected': True, 'check_only_wrote_nothing': True,
              'repeat_import_rejected': True, 'export_matches_import': True,
              'previous_test_files_unchanged': True, 'formal_data_unchanged': True,
              'browser_errors': errors}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'pipeline.log').write_text('\n'.join(logs), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'验收产物：{output}')


if __name__ == '__main__':
    main()
