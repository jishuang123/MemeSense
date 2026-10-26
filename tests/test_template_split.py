"""模板隔离、随机复现和 uncertain 规则测试。"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from memesense.data.split import split_by_template


class TemplateSplitTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'sample_id': f'M{i:04d}', 'template_id': f'T{(i-1)//3+1:04d}',
                      'intent_label': 'agree' if i % 2 else 'disagree'} for i in range(1, 31)]

    def test_isolation_reproducibility_and_complete_coverage(self):
        before = deepcopy(self.rows)
        parts, excluded = split_by_template(self.rows)
        self.assertEqual((parts, excluded), split_by_template(list(reversed(self.rows))))
        self.assertEqual(excluded, [])
        self.assertEqual(sorted(r['sample_id'] for part in parts.values() for r in part),
                         sorted(r['sample_id'] for r in self.rows))
        groups = [{r['template_id'] for r in part} for part in parts.values()]
        self.assertEqual([len(group) for group in groups], [8, 1, 1])
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertEqual(self.rows, before)
        self.assertNotEqual(parts, split_by_template(self.rows, seed=99)[0])

    def test_uncertain_exclusion_and_mixed_template(self):
        self.rows[0]['intent_label'] = 'uncertain'
        parts, excluded = split_by_template(self.rows)
        self.assertEqual(excluded, [self.rows[0]])
        self.assertEqual(sum(map(len, parts.values())), 29)
        self.assertEqual(split_by_template(self.rows, uncertain='include')[1], [])

    def test_all_uncertain_and_small_group_counts(self):
        rows = [{**r, 'intent_label': 'uncertain'} for r in self.rows[:9]]
        parts, excluded = split_by_template(rows)
        self.assertEqual(sum(map(len, parts.values())), 0)
        self.assertEqual(len(excluded), 9)
        parts, _ = split_by_template(rows, uncertain='include')
        self.assertEqual([len(part) for part in parts.values()], [3, 3, 3])
        parts, _ = split_by_template(self.rows[:3])
        self.assertEqual([len(part) for part in parts.values()], [3, 0, 0])

    def test_invalid_ratios_and_zero_ratio(self):
        for ratios in [(0.8, 0.2, 0.2), (-1, 1, 1), (float('nan'), 0, 1)]:
            with self.assertRaises(ValueError):
                split_by_template(self.rows, ratios=ratios)
        parts, _ = split_by_template(self.rows, ratios=(1, 0, 0))
        self.assertEqual([len(part) for part in parts.values()], [30, 0, 0])
        with self.assertRaises(ValueError):
            split_by_template(self.rows, uncertain='discard_silently')


if __name__ == '__main__':
    unittest.main()
