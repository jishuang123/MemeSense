"""统计报告及泄漏审计测试。"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from memesense.data.statistics import audit_dataset


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'sample_id': f'M{i:04d}', 'template_id': 'T0001' if i < 3 else 'T0003',
                      'intent_label': 'agree' if i < 3 else 'uncertain'} for i in (1, 2, 3)]
        self.parts = {'train': self.rows[:2], 'val': [], 'test': [], 'excluded_uncertain': self.rows[2:]}

    def test_counts_zero_labels_and_exclusion(self):
        report = audit_dataset(self.rows, self.parts, ['agree', 'uncertain', 'disagree'])
        self.assertTrue(report['checks']['passed'])
        self.assertEqual(report['source']['samples'], 3)
        self.assertEqual(report['source']['templates'], 2)
        self.assertEqual(report['source']['uncertain'], 1)
        self.assertEqual(report['source']['labels']['disagree'], 0)
        self.assertEqual(report['assigned']['samples'], 2)

    def test_template_leakage_without_duplicate_sample(self):
        self.parts['train'] = [self.rows[0]]
        self.parts['val'] = [self.rows[1]]
        report = audit_dataset(self.rows, self.parts, ['agree', 'uncertain'])
        self.assertFalse(report['checks']['passed'])
        self.assertEqual(report['checks']['template_overlaps']['train/val'], ['T0001'])
        self.assertFalse(report['checks']['duplicate_samples'])

    def test_duplicates_missing_and_modified_fields(self):
        self.parts['val'] = [self.rows[0]]
        self.parts['excluded_uncertain'] = []
        self.parts['test'] = [{**self.rows[1], 'intent_label': 'other'}]
        report = audit_dataset(self.rows, self.parts, ['agree', 'uncertain'])
        self.assertFalse(report['checks']['passed'])
        self.assertIn('M0001', report['checks']['duplicate_samples'])
        self.assertEqual(report['checks']['missing_samples'], ['M0003'])
        self.assertTrue(any('原字段' in e for e in report['errors']))

    def test_all_excluded_is_not_leakage(self):
        source = [{**row, 'intent_label': 'uncertain'} for row in self.rows]
        report = audit_dataset(source, {'train': [], 'val': [], 'test': [], 'excluded_uncertain': source}, ['uncertain'])
        self.assertTrue(report['checks']['passed'])
        self.assertFalse(report['checks']['template_leakage'])
        self.assertTrue(report['warnings'])


if __name__ == '__main__':
    unittest.main()
