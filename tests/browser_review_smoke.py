"""完整流水线与真实 Edge 浏览器验收，所有测试产物留在 outputs 独立目录。

运行：python tests/browser_review_smoke.py
需要额外测试依赖 playwright 以及本机 Microsoft Edge，不属于生产依赖。
"""

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def snapshot(directory: Path) -> dict[str, tuple[str, int]]:
    """记录文件内容散列及修改时间，用于验证输入没有变化。"""
    return {p.relative_to(directory).as_posix():
            (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in directory.rglob("*") if p.is_file()}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    formal_before = snapshot(ROOT / "data")
    run = Path(tempfile.mkdtemp(prefix="review_smoke_", dir=ROOT / "outputs"))
    print(f"测试目录：{run}", flush=True)
    raw = run / "fixtures"
    raw.mkdir()
    base = Image.new("RGB", (240, 180), "#e1f0ff")
    draw = ImageDraw.Draw(base)
    draw.ellipse((35, 25, 205, 155), fill="#3784ad", outline="black", width=4)
    draw.ellipse((80, 65, 95, 85), fill="white")
    draw.ellipse((145, 65, 160, 85), fill="white")
    draw.arc((80, 85, 165, 125), 0, 180, fill="black", width=4)
    base.save(raw / "a_fish.png")
    base.save(raw / "b_copy.png")
    base.resize((360, 270)).save(raw / "c_resized.jpg", quality=90)
    other = Image.new("RGB", (240, 180), "white")
    draw = ImageDraw.Draw(other)
    for x in range(0, 240, 40):
        draw.rectangle((x, 0, x + 17, 179), fill="black")
    other.save(raw / "d_stripes.webp")
    (raw / "broken.png").write_bytes(b"intentional invalid test image")
    index, grouped, pairs, page = (run / name for name in
                                 ("index.csv", "grouped.csv", "pairs.csv", "review.html"))
    logs = []

    def command(script: str, *args: object) -> str:
        result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script),
                                 *map(str, args)], cwd=ROOT, capture_output=True, encoding="utf-8")
        logs.append(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
        return result.stderr

    assert "WARNING" in command("prepare_data.py", "--input", raw, "--output", index)
    first = read_csv(index)
    assert len(first) == 4
    command("prepare_data.py", "--input", raw, "--output", index)
    assert read_csv(index) == first
    # 新图排在前面，验证仍然续号。
    other.rotate(90, expand=True).save(raw / "0_new.png")
    raw_before = snapshot(raw)
    command("prepare_data.py", "--input", raw, "--output", index)
    indexed = read_csv(index)
    assert indexed[:4] == first and indexed[-1]["sample_id"] == "M0005"
    index_before = index.read_bytes()
    command("deduplicate.py", "--input", index, "--output", grouped, "--pairs", pairs)
    grouped_rows = read_csv(grouped)
    assert grouped_rows[0]["template_id"] == grouped_rows[1]["template_id"]
    assert read_csv(pairs), "应包含相同图片的直接匹配对"
    grouped_before = grouped.read_bytes()
    command("build_review_page.py", "--input", grouped, "--images", raw, "--output", page)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True, timeout=20000)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1050})
        tab = context.new_page()
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.goto(page.as_uri())
        expect(tab.locator('.card')).to_have_count(5)
        # 页面采用懒加载，需要逐张进入视口后检查解码结果。
        for image in tab.locator('.preview img').all():
            image.scroll_into_view_if_needed()
            image.evaluate('(image) => image.decode()')
        assert tab.locator('.preview img').evaluate_all(
            '(images) => images.every(image => image.complete && image.naturalWidth > 0)')
        group = tab.locator('.group').filter(has=tab.get_by_role('textbox', name='M0001 的候选 template_id', exact=True))
        group.get_by_role('button', name='分组正确', exact=True).click()
        expect(group.locator('.group-status')).to_have_text('分组正确')
        group.get_by_role('button', name='疑似误分组', exact=True).click()
        expect(group.locator('.group-status')).to_have_text('疑似误分组')
        group.get_by_role('button', name='设为未复核', exact=True).click()
        expect(group.locator('.group-status')).to_have_text('未复核')
        group.get_by_role('button', name='分组正确', exact=True).click()
        tab.get_by_role('textbox', name='M0002 的候选 template_id', exact=True).fill('T0099')
        expect(group.locator('.group-status')).to_have_text('未复核')
        group.get_by_role('button', name='疑似误分组', exact=True).click()
        group.locator('.reference').select_option(label='M0002')
        assert all('距 M0002' in text for text in group.locator('.distance').all_text_contents())
        group.locator('.preview').first.click()
        expect(tab.locator('#zoom')).to_be_visible()
        tab.get_by_role('button', name='关闭', exact=True).click()
        tab.screenshot(path=str(run / "review_desktop.png"), full_page=True)
        # 隐藏所有样本后导出，确认下载仍包含全部行。
        tab.locator('#search').fill('no-such-sample')
        expect(tab.locator('.group:visible')).to_have_count(0)
        with tab.expect_download() as download_info:
            tab.get_by_role('button', name='导出复核 CSV', exact=True).click()
        download = download_info.value
        assert download.suggested_filename.startswith('meme_index_reviewed_')
        exported_path = run / download.suggested_filename
        download.save_as(exported_path)
        assert download.failure() is None
        reviewed = read_csv(exported_path)
        assert len(reviewed) == 5
        source_by_id = {row['sample_id']: row for row in grouped_rows}
        for row in reviewed:
            original = source_by_id[row['sample_id']]
            for key, value in original.items():
                if key != 'template_id':
                    assert row[key] == value, (row['sample_id'], key)
            assert row['review_original_template_id'] == original['template_id']
        edited = next(row for row in reviewed if row['sample_id'] == 'M0002')
        assert edited['template_id'] == 'T0099' and edited['review_status'] == 'suspected'
        assert any(row['review_status'] == 'pending' for row in reviewed)
        tab.locator('#search').fill('')
        tab.set_viewport_size({'width': 390, 'height': 844})
        tab.screenshot(path=str(run / "review_mobile.png"), full_page=True)
        assert tab.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        # 下载文件重新生成页面，验证拆组和复核状态保留。
        resumed = run / 'review_resumed.html'
        command('build_review_page.py', '--input', exported_path, '--images', raw, '--output', resumed)
        tab.goto(resumed.as_uri())
        card = tab.locator('.card').filter(has=tab.get_by_role('textbox', name='M0002 的候选 template_id', exact=True))
        expect(card.locator('.template-edit')).to_have_value('T0099')
        expect(card.locator('.sample-status')).to_have_text('疑似误分组')
        assert not errors, errors
        version = browser.version
        browser.close()
    assert raw_before == snapshot(raw), '测试原图被修改'
    assert index_before == index.read_bytes(), '测试索引被修改'
    assert grouped_before == grouped.read_bytes(), '候选索引被修改'
    assert formal_before == snapshot(ROOT / 'data'), '正式数据目录被修改'
    (run / 'pipeline.log').write_text('\n'.join(logs), encoding='utf-8')
    report = {'passed': True, 'browser': f'Microsoft Edge {version} (headless)',
              'samples': 5, 'corrupt_files_skipped': 1,
              'templates': len({r['template_id'] for r in grouped_rows}),
              'direct_pairs': len(read_csv(pairs)), 'export': exported_path.name,
              'browser_errors': errors, 'original_images_unchanged': True,
              'formal_data_unchanged': True, 'input_csv_unchanged': True,
              'checks': ['repeat_index', 'increment_id', 'phash_grouping', 'thumbnails',
                         'correct_suspected_pending_marks', 'edit_resets_status',
                         'reference_switch', 'zoom', 'export_hidden_samples',
                         'csv_values_preserved', 'mobile_layout', 'resume_export']}
    (run / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'验收产物：{run}')


if __name__ == '__main__':
    main()
