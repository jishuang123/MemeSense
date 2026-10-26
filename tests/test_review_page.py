"""离线复核页的缩略图、距离数据和只读边界测试。"""

import hashlib
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import shutil
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_review_page import render_page, thumbnail_data
from prepare_data import save_index


def sample(number: int, path: str, phash: str = "0000000000000000") -> dict[str, str]:
    return {"sample_id": f"M{number:04d}", "original_filename": path,
            "image_path": path, "width": "40", "height": "30", "file_size": "100",
            "phash": phash, "template_id": "T0001", "ocr_text": "", "source": "unknown"}


class ReviewPageTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "JavaScript 导出测试需要 Node.js")
    def test_review_edit_status_and_csv_roundtrip(self):
        rows = [sample(1, '中文,图片.png'), sample(2, 'two.png')]
        rows[0]['notes'] = '逗号,双引号"和\n换行</script>'
        rows[1]['notes'] = ''
        script = r'''
const assert = require('node:assert/strict');
const logic = require('./scripts/review_logic.js');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const rows = logic.createReviewRows(input);
logic.markReviewGroup(rows, ['M0001', 'M0002'], 'correct');
assert.equal(rows[1].review_status, 'correct');
logic.editReviewTemplate(rows, ['M0001', 'M0002'], 'M0002', 'T0099');
assert.equal(rows[0].review_status, 'pending');
assert.equal(rows[1].review_status, 'pending');
logic.markReviewGroup(rows, ['M0001', 'M0002'], 'suspected');
assert.equal(rows[0].review_status, 'suspected');
assert.equal(input[1].template_id, 'T0001');
assert.equal(rows[1].review_original_template_id, 'T0001');
assert.deepEqual(logic.createReviewRows(rows), rows);
process.stdout.write(logic.reviewCSV(rows, Object.keys(input[0])));
'''
        result = subprocess.run(['node', '-e', script], input=json.dumps(rows),
                                capture_output=True, encoding='utf-8', cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = list(csv.DictReader(io.StringIO(result.stdout.lstrip('\ufeff'))))
        self.assertEqual(len(exported), 2)
        self.assertEqual(exported[0]['notes'], rows[0]['notes'])
        self.assertEqual(exported[1]['template_id'], 'T0099')
        self.assertEqual(exported[0]['review_status'], 'suspected')
        self.assertEqual(exported[1]['review_original_template_id'], 'T0001')

    def test_export_payload_preserves_extra_fields_and_source_order(self):
        rows = [sample(2, 'missing.png'), sample(1, 'also-missing.png')]
        rows[0]['notes'] = '</script><script>bad()</script>'
        with self.assertLogs('build_review_page', level='WARNING'):
            page = render_page(rows, ROOT / 'data/raw/images')
        payload = json.loads(re.search(r'<script id="review-records" type="application/json">(.*?)</script>', page).group(1))
        self.assertEqual(payload['rows'], rows)
        self.assertIn('notes', payload['fields'])
        self.assertNotIn('</script><script>bad()</script>', page)
        self.assertIn('data-status="correct"', page)
        self.assertIn('data-status="suspected"', page)

    def test_embedded_thumbnail_escaped_content_and_raw_unchanged(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            root = Path(directory)
            image = root / "中文 #1.png"
            Image.new("RGB", (640, 480), "blue").save(image)
            before = (hashlib.sha256(image.read_bytes()).hexdigest(), image.stat().st_mtime_ns)
            row = sample(1, image.name)
            row["template_id"] = '<script>alert("bad")</script>'
            page = render_page([row], root)
            self.assertIn("data:image/png;base64,", page)
            self.assertIn("&lt;script&gt;", page)
            self.assertNotIn('<script>alert("bad")</script>', page)
            self.assertEqual(before, (hashlib.sha256(image.read_bytes()).hexdigest(), image.stat().st_mtime_ns))
            self.assertNotIn("{{CONTENT}}", page)

    def test_missing_image_invalid_hash_and_reference_order(self):
        rows = [sample(3, "missing.png", "invalid"), sample(1, "one.png"),
                sample(2, "two.png", "0000000000000003")]
        with self.assertLogs("build_review_page", level="WARNING"):
            page = render_page(rows, ROOT / "data/raw/images", 1)
        self.assertIn("图片缺失、损坏或路径不可用", page)
        data = json.loads(re.search(r'<script id="review-data" type="application/json">(.*?)</script>', page).group(1))
        self.assertEqual([item["sample_id"] for item in data[0]], ["M0001", "M0002", "M0003"])
        self.assertEqual(data[0][-1]["phash"], "")
        self.assertEqual((int(data[0][0]["phash"], 16) ^ int(data[0][1]["phash"], 16)).bit_count(), 2)

    def test_empty_and_path_escape(self):
        self.assertIn("暂无样本", render_page([], ROOT / "data/raw/images"))
        with self.assertRaises(ValueError):
            thumbnail_data("../outside.png", ROOT / "data/raw/images")

    def test_cli_preserves_csv_and_rejects_raw_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            root = Path(directory)
            raw = root / "raw"
            raw.mkdir()
            Image.new("RGB", (40, 30)).save(raw / "one.png")
            source, output = root / "index.csv", root / "review.html"
            save_index(source, [sample(1, "one.png")])
            before = source.read_bytes()
            command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/build_review_page.py"),
                       "--input", str(source), "--images", str(raw), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("data:image/png;base64,", output.read_text(encoding="utf-8"))
            self.assertEqual(source.read_bytes(), before)
            result = subprocess.run(command + ["--output", str(raw / "review.html")], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((raw / "review.html").exists())


if __name__ == "__main__":
    unittest.main()
