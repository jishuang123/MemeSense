"""独立测试数据上的真实浏览器标注与 CSV 下载验收。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from playwright.sync_api import sync_playwright, expect
from browser_review_smoke import ROOT, read_csv, snapshot


def main():
    source = ROOT / 'outputs/review_import_smoke_8yaeef1_/meme_index_reviewed.csv'
    fixtures = ROOT / 'outputs/review_smoke_nefqxagt/fixtures'
    original = source.read_bytes()
    formal_before, raw_before = snapshot(ROOT / 'data'), snapshot(fixtures)
    output = Path(tempfile.mkdtemp(prefix='annotation_smoke_', dir=ROOT / 'outputs'))
    page = output / 'intent_annotation.html'
    def generate(input_path, output_path):
        result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/build_annotation_page.py'),
                                 '--input', str(input_path), '--images', str(fixtures), '--output', str(output_path)],
                                capture_output=True, encoding='utf-8')
        assert result.returncode == 0, result.stderr
    generate(source, page)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge', headless=True, timeout=20000)
        context=browser.new_context(accept_downloads=True,viewport={'width':1440,'height':1050})
        tab=context.new_page()
        tab.on('pageerror',lambda error:errors.append(str(error)))
        tab.goto(page.as_uri())
        expect(tab.locator('.card')).to_have_count(5)
        for image in tab.locator('img').all():
            image.scroll_into_view_if_needed(); image.evaluate('(image)=>image.decode()')
        tab.get_by_label('M0001 意图',exact=True).select_option('agree')
        expect(tab.locator('#progress')).to_contain_text('已填写 1 / 5')
        # 合成图片没有对话语境，最终标签设为无法判断，不能伪造语义真值。
        tab.get_by_label('M0001 意图',exact=True).select_option('uncertain')
        note='测试备注：缺少语境，含逗号,双引号"\n换行。仅验证标注功能。'
        tab.get_by_label('M0001 备注',exact=True).fill(note)
        tab.get_by_label('M0002 意图',exact=True).select_option('uncertain')
        tab.get_by_label('M0002 备注',exact=True).fill('合成测试图片，无上下文。')
        # 清空标签应恢复为未标注，备注不丢失。
        tab.get_by_label('M0002 意图',exact=True).select_option('')
        expect(tab.locator('#progress')).to_contain_text('已填写 1 / 5')
        tab.screenshot(path=str(output/'annotation_desktop.png'),full_page=True)
        tab.locator('#pending').check()
        expect(tab.locator('.card:visible')).to_have_count(4)
        with tab.expect_download() as info:
            tab.get_by_role('button',name='导出标注 CSV',exact=True).click()
        download=info.value
        exported=output/download.suggested_filename
        download.save_as(exported)
        assert download.failure() is None
        rows=read_csv(exported)
        assert len(rows)==5
        for original_row,row in zip(read_csv(source),rows):
            assert all(row[key]==value for key,value in original_row.items())
            assert row['label_schema_version']=='intent-draft-v1'
        assert rows[0]['intent_label']=='uncertain' and rows[0]['annotation_notes']==note
        assert rows[0]['annotation_status']=='annotated'
        assert rows[1]['annotation_status']=='pending' and rows[1]['annotation_notes']=='合成测试图片，无上下文。'
        resumed=output/'annotation_resumed.html'
        generate(exported,resumed)
        tab.goto(resumed.as_uri())
        expect(tab.get_by_label('M0001 意图',exact=True)).to_have_value('uncertain')
        expect(tab.get_by_label('M0001 备注',exact=True)).to_have_value(note)
        tab.set_viewport_size({'width':390,'height':844})
        tab.screenshot(path=str(output/'annotation_mobile.png'),full_page=True)
        assert tab.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        assert not errors,errors
        version=browser.version
        browser.close()
    assert source.read_bytes()==original
    assert snapshot(ROOT/'data')==formal_before and snapshot(fixtures)==raw_before
    report={'passed':True,'browser':f'Edge {version} headless','samples':5,'annotated':1,'pending':4,
            'export':exported.name,'source_and_images_unchanged':True,'formal_data_unchanged':True,
            'checks':['label_selection','notes','clear_label','pending_filter','export_all_rows',
                      'csv_special_characters','resume_annotations','mobile_layout'],'browser_errors':errors}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(output)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
