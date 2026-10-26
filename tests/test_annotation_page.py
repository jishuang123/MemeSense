"""标签配置和标注输入边界测试。"""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_annotation_page import load_labels, annotation_rows
from test_review_page import sample


class AnnotationTests(unittest.TestCase):
    def test_config_draft_and_invalid_labels(self):
        config = load_labels(ROOT / 'configs/labels.yaml')
        self.assertIn('uncertain', config['labels'])
        self.assertNotIn('happy', config['labels'])
        with tempfile.TemporaryDirectory(dir=ROOT / 'outputs') as directory:
            path = Path(directory) / 'labels.yaml'
            path.write_text('version: v1\nlabels: [agree, agree]\ndescriptions: {agree: yes}', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_labels(path)

    def test_requires_review_and_valid_resumed_annotation(self):
        config = load_labels(ROOT / 'configs/labels.yaml')
        with tempfile.TemporaryDirectory(dir=ROOT / 'outputs') as directory:
            path = Path(directory) / 'index.csv'
            row = {**sample(1, 'one.png'), 'review_status': 'correct', 'review_original_template_id': 'T0001'}
            def save():
                with path.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader(); writer.writerow(row)
            save()
            _, rows = annotation_rows(path, config)
            self.assertEqual(rows[0]['annotation_status'], 'pending')
            for key, value in [('review_status', 'pending'), ('intent_label', 'happy'),
                               ('label_schema_version', 'old-v1'), ('annotation_status', 'annotated')]:
                with self.subTest(key=key):
                    previous = row.copy()
                    row[key] = value
                    save()
                    with self.assertRaises(ValueError):
                        annotation_rows(path, config)
                    row = previous


if __name__ == '__main__':
    unittest.main()
