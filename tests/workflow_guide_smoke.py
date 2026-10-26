"""从全新目录执行指南中的 PowerShell 命令及浏览器人工步骤。"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect
from browser_review_smoke import ROOT, read_csv, snapshot


def main() -> None:
    guide = (ROOT / 'docs/dataset_workflow.md').read_text(encoding='utf-8')
    blocks = re.findall(r'```powershell\n(.*?)```', guide, re.S)
    output = Path(tempfile.mkdtemp(prefix='guide_e2e_', dir=ROOT / 'outputs'))
    print(f'全新验收目录：{output}', flush=True)
    formal_before = snapshot(ROOT / 'data')
    prior_files = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (ROOT / 'outputs').rglob('*.csv')
                   if not p.is_relative_to(output)}
    command_dir = output / 'commands'
    command_dir.mkdir()
    sandbox = output / 'dataset'
    images, interim, annotations, processed, views = [sandbox / name for name in
                                                    ('images', 'interim', 'annotations', 'processed', 'pages')]
    logs, completed = [], []
    preamble = f'''$ErrorActionPreference = 'Stop'
$Sandbox = '{sandbox.as_posix()}'
$Images = "$Sandbox/images"
$MasterIndex = "$Sandbox/meme_index.csv"
$Interim = "$Sandbox/interim"
$Annotations = "$Sandbox/annotations"
$Processed = "$Sandbox/processed"
$Views = "$Sandbox/pages"
$Labels = "$Interim/labels.yaml"
'''

    def block_start(prefix):
        return next(block for block in blocks if block.startswith(prefix))

    def run_block(name, text):
        # 路径取新目录；Python 使用指南允许的虚拟环境解释器替代形式。
        lines = []
        for line in text.splitlines():
            if line.startswith('Invoke-Item'):
                continue  # 紧接着由真实 Edge 打开同一路径，不打开个人浏览器会话。
            if line.startswith('$Sandbox ='):
                line = f"$Sandbox = '{sandbox.as_posix()}'"
            if line.startswith('python '):
                lines.append(f"& '{sys.executable}' -X utf8 " + line[len('python '):])
                lines.append('if ($LASTEXITCODE -ne 0) { throw "Python step failed: $LASTEXITCODE" }')
            else:
                lines.append(line)
        script = command_dir / f'{name}.ps1'
        script.write_text(preamble + '\n'.join(lines), encoding='utf-8-sig')
        result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-File', str(script)],
                                cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace')
        logs.append(f'[{name}]\n{result.stdout}\n{result.stderr}')
        assert result.returncode == 0, logs[-1]
        completed.append(name)

    run_block('01_test_paths', block_start("$Sandbox = 'outputs/manual_dataset_test_v001'"))
    # 全新合成图片，非复用历史 CSV 或原图。放入后即固定字节与修改时间。
    base = Image.new('RGB', (240, 180), '#e7effa')
    draw = ImageDraw.Draw(base)
    draw.ellipse((35, 20, 205, 160), fill='#4a9bac', outline='black', width=3)
    draw.ellipse((75, 55, 90, 75), fill='white')
    draw.ellipse((150, 55, 165, 75), fill='white')
    draw.arc((75, 80, 165, 130), 0, 180, fill='black', width=4)
    base.save(images / '01_face.png')
    base.save(images / '02_copy.PNG')
    base.resize((360, 270)).save(images / '03_resized.jpg', quality=90)
    stripes = Image.new('RGB', (240, 180), 'white')
    draw = ImageDraw.Draw(stripes)
    for x in range(0, 240, 40):
        draw.rectangle((x, 0, x + 18, 180), fill='black')
    stripes.save(images / '04_stripes.webp')
    stripes.rotate(90, expand=True).save(images / '05_horizontal.jpeg')
    (images / 'broken.png').write_bytes(b'corrupt image for isolated testing')
    raw_before = snapshot(images)
    run_block('02_batch_directories', block_start('foreach ($Directory'))
    assert (interim / 'labels.yaml').read_bytes() == (ROOT / 'configs/labels.yaml').read_bytes()
    run_block('03_index', block_start('python scripts/prepare_data.py'))
    assert len(read_csv(interim / 'meme_index.csv')) == 5
    assert (interim / 'meme_index.csv').read_bytes() == (sandbox / 'meme_index.csv').read_bytes()
    index_before = (interim / 'meme_index.csv').read_bytes()
    run_block('04_templates', block_start('python scripts/deduplicate.py'))
    grouped = read_csv(interim / 'meme_index_with_templates.csv')
    assert grouped[0]['template_id'] == grouped[1]['template_id'] == grouped[2]['template_id']
    assert len({r['template_id'] for r in grouped}) == 3
    baseline_before = (interim / 'meme_index_with_templates.csv').read_bytes()
    run_block('05_review_page', block_start('python scripts/build_review_page.py --input "$Interim'))
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True, timeout=20000)
        context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1050})
        tab = context.new_page()
        tab.on('pageerror', lambda error: errors.append(str(error)))
        def open_page(path):
            tab.goto(path.as_uri())
            for image in tab.locator('img').all():
                if image.is_visible():
                    image.scroll_into_view_if_needed()
                    image.evaluate('(image) => image.decode()')
        def download(name, destination):
            assert not destination.exists()
            with tab.expect_download() as event:
                tab.get_by_role('button', name=name, exact=True).click()
            event.value.save_as(destination)
            assert event.value.failure() is None
        open_page(views / 'template_review.html')
        for group in tab.locator('.group').all():
            group.get_by_role('button', name='分组正确', exact=True).click()
        # 阶段性下载、重新生成页面验证指南的恢复路径。
        download('导出复核 CSV', annotations / 'review_export.csv')
        run_block('06_review_resume', block_start('python scripts/build_review_page.py --input "$Annotations'))
        open_page(views / 'template_review_v2.html')
        assert tab.locator('.sample-status').all_text_contents() == ['分组正确'] * 5
        download('导出复核 CSV', annotations / 'review_export_v2.csv')
        tab.screenshot(path=str(output / 'template_review.png'), full_page=True)
        run_block('07_review_import', block_start('python scripts/import_reviewed.py').replace('review_export.csv', 'review_export_v2.csv'))
        reviewed_before = (processed / 'meme_index_reviewed.csv').read_bytes()
        run_block('08_annotation_page', block_start('python scripts/build_annotation_page.py --input "$Processed'))
        open_page(views / 'intent_annotation.html')
        tab.get_by_label('M0001 意图', exact=True).select_option('uncertain')
        tab.get_by_label('M0001 备注', exact=True).fill('全新独立测试图片，无对话语境，无法判断。')
        download('导出标注 CSV', annotations / 'intent_export.csv')
        run_block('09_annotation_resume', block_start('python scripts/build_annotation_page.py --input "$Annotations'))
        open_page(views / 'intent_annotation_v2.html')
        expect(tab.get_by_label('M0001 意图', exact=True)).to_have_value('uncertain')
        for i in range(2, 6):
            tab.get_by_label(f'M{i:04d} 意图', exact=True).select_option('uncertain')
            tab.get_by_label(f'M{i:04d} 备注', exact=True).fill('合成测试图片，缺少交流语境；仅验证数据流程。')
        expect(tab.locator('#progress')).to_contain_text('已填写 5 / 5')
        download('导出标注 CSV', annotations / 'intent_export_v2.csv')
        tab.screenshot(path=str(output / 'intent_annotation.png'), full_page=True)
        run_block('10_annotation_import', block_start('python scripts/import_annotations.py').replace('intent_export.csv', 'intent_export_v2.csv'))
        annotated_before = (processed / 'meme_index_annotated.csv').read_bytes()
        assert read_csv(processed / 'meme_index_annotated.csv') == read_csv(annotations / 'intent_export_v2.csv')
        run_block('11_split_default', block_start('python scripts/split_dataset.py'))
        assert len(read_csv(processed / 'splits/excluded_uncertain.csv')) == 5
        assert all(not read_csv(processed / f'splits/{n}.csv') for n in ('train', 'val', 'test'))
        run_block('12_report_default', block_start('python scripts/dataset_report.py'))
        open_page(views / 'dataset_report/dataset_report.html')
        expect(tab.locator('.status')).to_have_text('审计通过')
        expect(tab.locator('body')).to_contain_text('三个集合均为空')
        tab.screenshot(path=str(output / 'default_report.png'), full_page=True)
        # 指南说明的 include 分支，另用新目录，仅测试整组隔离。
        run_block('13_split_include', block_start('python scripts/split_dataset.py').replace('$Processed/splits', '$Processed/splits_include').replace('--uncertain exclude', '--uncertain include'))
        run_block('14_report_include', block_start('python scripts/dataset_report.py').replace('$Processed/splits', '$Processed/splits_include').replace('$Views/dataset_report', '$Views/dataset_report_include'))
        open_page(views / 'dataset_report_include/dataset_report.html')
        expect(tab.locator('.status')).to_have_text('审计通过')
        tab.screenshot(path=str(output / 'include_report.png'), full_page=True)
        assert not errors, errors
        version = browser.version
        browser.close()
    assert (interim / 'meme_index.csv').read_bytes() == index_before
    assert (interim / 'meme_index_with_templates.csv').read_bytes() == baseline_before
    assert (processed / 'meme_index_reviewed.csv').read_bytes() == reviewed_before
    assert (processed / 'meme_index_annotated.csv').read_bytes() == annotated_before
    assert snapshot(images) == raw_before and snapshot(ROOT / 'data') == formal_before
    for path, state in prior_files.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == state
    include = json.loads((processed / 'splits_include/split_report.json').read_text(encoding='utf-8'))
    report = {'passed': True, 'fresh_data_only': True, 'browser': f'Edge {version} headless',
              'completed_steps': completed, 'samples': 5, 'templates': 3, 'corrupt_skipped': 1,
              'default_excluded': 5, 'include_split_counts': {k: v['samples'] for k, v in include['splits'].items()},
              'template_leakage': include['template_leakage'], 'browser_resume_and_download_verified': True,
              'raw_images_formal_data_and_previous_indices_unchanged': True, 'browser_errors': errors}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'pipeline.log').write_text('\n'.join(logs), encoding='utf-8')
    print(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
