"""意图标注导入验收：字段约束、来源一致性和不覆盖。"""

import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from build_annotation_page import load_labels
from memesense.data.annotation_import import ANNOTATION_FIELDS, validate_annotations
from test_review_page import sample


class AnnotationImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'outputs')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.base = self.root / 'annotations.csv', self.root / 'reviewed.csv'
        self.config = load_labels(ROOT / 'configs/labels.yaml')
        self.originals = [{**sample(i, f'{i}.png'), 'review_status': 'correct',
                           'review_original_template_id': 'T0001', 'custom': '保留'} for i in (1, 2)]
        self.rows = [{**row, 'intent_label': 'uncertain', 'annotation_notes': '中文,引号"\n换行',
                      'annotation_status': 'annotated', 'label_schema_version': self.config['version']}
                     for row in self.originals]
        self.write(self.base, self.originals)

    def write(self, path, rows, fields=None):
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    def validate(self, complete=True):
        self.write(self.source, self.rows)
        return validate_annotations(self.source, self.base, self.config, complete)

    def test_complete_and_pending_rules(self):
        _, rows, counts = self.validate()
        self.assertEqual(rows, self.rows)
        self.assertEqual(counts, {'annotated': 2, 'pending': 0})
        self.rows[1].update(intent_label='', annotation_status='pending')
        with self.assertRaisesRegex(ValueError, '未标注'):
            self.validate()
        self.assertEqual(self.validate(False)[2]['pending'], 1)

    def test_invalid_label_status_version_and_sample(self):
        for field, value in [('sample_id', 'M0000'), ('sample_id', 'M0002'),
                             ('intent_label', 'happy'), ('intent_label', ''),
                             ('annotation_status', 'done'), ('annotation_status', 'pending'),
                             ('label_schema_version', ''), ('label_schema_version', 'old-v1')]:
            with self.subTest(field=field, value=value):
                old = self.rows[0][field]
                self.rows[0][field] = value
                with self.assertRaises(ValueError):
                    self.validate(False)
                self.rows[0][field] = old

    def test_source_fields_and_sample_set(self):
        for field in ['template_id', 'review_status', 'image_path', 'phash', 'custom']:
            old = self.rows[0][field]
            self.rows[0][field] = 'changed'
            with self.assertRaisesRegex(ValueError, '原字段'):
                self.validate()
            self.rows[0][field] = old
        removed = self.rows.pop()
        with self.assertRaisesRegex(ValueError, '遗漏样本'):
            self.validate()
        self.rows.append(removed)
        self.rows[1]['sample_id'] = 'M9999'
        with self.assertRaisesRegex(ValueError, '不在来源'):
            self.validate()

    def test_missing_columns_and_unreviewed_source(self):
        for field in ANNOTATION_FIELDS:
            changed = [{k: v for k, v in row.items() if k != field} for row in self.rows]
            self.write(self.source, changed)
            with self.assertRaisesRegex(ValueError, '缺少字段'):
                validate_annotations(self.source, self.base, self.config)
        self.originals[0]['review_status'] = 'pending'
        self.write(self.base, self.originals)
        with self.assertRaisesRegex(ValueError, '尚未完成模板复核'):
            self.validate()

    def test_cli_preserves_sources_and_refuses_overwrite(self):
        self.validate()
        original = self.source.read_bytes(), self.base.read_bytes()
        output = self.root / 'accepted.csv'
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/import_annotations.py'),
                   '--input', str(self.source), '--baseline', str(self.base), '--output', str(output)]
        checked = subprocess.run(command + ['--check-only'], capture_output=True)
        self.assertEqual(checked.returncode, 0)
        self.assertFalse(output.exists())
        result = subprocess.run(command, capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        with output.open(encoding='utf-8-sig', newline='') as stream:
            self.assertEqual(list(csv.DictReader(stream)), self.rows)
        saved = output.read_bytes()
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual(output.read_bytes(), saved)
        self.assertNotEqual(subprocess.run(command + ['--output', str(self.base)], capture_output=True).returncode, 0)
        forbidden = ROOT / 'data/raw/annotation_forbidden.csv'
        self.assertNotEqual(subprocess.run(command + ['--output', str(forbidden)], capture_output=True).returncode, 0)
        self.assertFalse(forbidden.exists())
        self.assertEqual((self.source.read_bytes(), self.base.read_bytes()), original)


if __name__ == '__main__':
    unittest.main()
