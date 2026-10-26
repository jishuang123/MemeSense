"""真实 Edge 打开三种独立统计报告，按 CSV 重算核对页面单元格。"""
from collections import Counter
import json
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright, expect
from browser_review_smoke import ROOT, read_csv, snapshot


def main() -> None:
    reports = ROOT / 'outputs/dataset_report_smoke_q6167p7h'
    source_dir = ROOT / 'outputs/browser_annotation_import_g64by_pq'
    split_dir = ROOT / 'outputs/template_split_smoke_8yfstjk0'
    protected = [ROOT / 'data', reports, source_dir, split_dir, ROOT / 'outputs/review_smoke_nefqxagt']
    before = [snapshot(path) for path in protected]
    output = Path(tempfile.mkdtemp(prefix='browser_dataset_report_', dir=ROOT / 'outputs'))
    results, errors = {}, []
    cases = [('include_report', [1, 3, 1], False), ('exclude_report', [0, 0, 0], False),
             ('leakage_report', [2, 2, 1], True)]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True, timeout=20000)
        tab = browser.new_page(viewport={'width': 1440, 'height': 1000})
        tab.on('pageerror', lambda error: errors.append(str(error)))
        for name, expected_counts, leakage in cases:
            folder = reports / name
            metadata = json.loads((folder / 'dataset_report.json').read_text(encoding='utf-8'))
            source = read_csv(Path(metadata['input']))
            partitions = {key: read_csv(Path(metadata['splits_dir']) / f'{key}.csv')
                          for key in ('train', 'val', 'test', 'excluded_uncertain')}
            assert len(source) == 5 and len({r['template_id'] for r in source}) == 3
            assert [len(partitions[key]) for key in ('train', 'val', 'test')] == expected_counts
            tab.goto((folder / 'dataset_report.html').as_uri())
            expect(tab.locator('h1')).to_have_text('MemeSense · 数据集统计')
            expect(tab.locator('.status')).to_have_text('审计失败，请先修复划分' if leakage else '审计通过')
            scopes = [('已标注索引', source),
                      ('已纳入划分（合计）', [r for key in ('train', 'val', 'test') for r in partitions[key]]),
                      *partitions.items()]
            for scope, rows in scopes:
                row = tab.locator('table').nth(0).locator('tr').filter(has=tab.get_by_role('rowheader', name=scope, exact=True))
                expected = [str(len(rows)), str(len({r['sample_id'] for r in rows})),
                            str(len({r['template_id'] for r in rows})),
                            str(sum(r['intent_label'] == 'uncertain' for r in rows)),
                            f'{len(rows) / len(source) * 100:.1f}%']
                assert row.locator('td').all_text_contents() == expected, (name, scope)
            # 全部标签，包括零计数类别，逐格与 CSV 独立统计对照。
            label_rows = tab.locator('table').nth(1).locator('tr').all()[1:]
            assert len(label_rows) == 11
            for row in label_rows:
                label = row.locator('th').evaluate('(cell) => cell.childNodes[0].textContent.trim()')
                counts = [Counter(r['intent_label'] for r in source)[label]]
                counts += [Counter(r['intent_label'] for r in rows)[label] for rows in partitions.values()]
                assert [int(v) for v in row.locator('td').all_text_contents()] == counts
            overlap_section = tab.locator('section').filter(has=tab.get_by_role('heading', name='模板跨集合检查', exact=True))
            expect(overlap_section).to_contain_text('train/val：T0001' if leakage else 'train/val：无交叉')
            expect(overlap_section).to_contain_text('train/test：无交叉')
            expect(overlap_section).to_contain_text('val/test：无交叉')
            notices = tab.locator('section').filter(has=tab.get_by_role('heading', name='错误与提示', exact=True))
            if leakage:
                expect(notices).to_contain_text('模板跨集合 train/val：T0001')
            if name == 'exclude_report':
                expect(notices).to_contain_text('三个集合均为空，当前没有可用于训练评估的样本。')
            else:
                expect(notices).to_contain_text('划分内全部为“无法判断”')
            tab.screenshot(path=str(output / f'{name}_desktop.png'), full_page=True)
            tab.set_viewport_size({'width': 390, 'height': 844})
            assert tab.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            tab.screenshot(path=str(output / f'{name}_mobile.png'), full_page=True)
            tab.set_viewport_size({'width': 1440, 'height': 1000})
            results[name] = {'samples': 5, 'templates': 3, 'uncertain': 5,
                             'train_val_test': expected_counts,
                             'excluded': len(partitions['excluded_uncertain']),
                             'template_leakage': leakage, 'all_cells_match_csv': True,
                             'warnings_visible': True, 'mobile_no_page_overflow': True}
        assert not errors, errors
        version = browser.version
        browser.close()
    assert before == [snapshot(path) for path in protected]
    report = {'passed': True, 'browser': f'Edge {version} headless', 'cases': results,
              'input_files_and_original_images_unchanged': True, 'browser_errors': errors}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
