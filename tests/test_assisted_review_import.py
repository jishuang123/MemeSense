"""只使用临时测试答案，不生成真实人工记录。"""
import csv
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'src')]
from import_assisted_review import load_batch
from memesense.data.assisted_review_import import validate, read_rows


class AssistedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'outputs')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder/'TEST_ONLY.csv'

    def write(self, rows):
        with self.source.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    def prepared(self, batch):
        expected, base, labels, _ = load_batch(batch)
        rows = deepcopy(expected)
        for r in rows:
            r.update(human_label='uncertain', human_note='TEST_ONLY, "quoted"\nline',
                     human_review_status='reviewed', reviewer_id='TEST_ONLY')
        return expected, base, labels, rows

    def test_all_seven_batches_and_versions(self):
        for n in range(1,8):
            with self.subTest(batch=n):
                expected, base, labels, rows = self.prepared(f'batch{n:02d}')
                self.write(rows)
                result, counts = validate(self.source, expected, base, labels)
                self.assertEqual(counts['pending'], 0)
                self.assertEqual(result[0]['label_schema_version'], 'intent-calibration-v2')
                self.assertEqual(result[0]['baseline_label_schema_version'], 'intent-draft-v1')
                for r, source in zip(result, rows):
                    for k,v in source.items(): self.assertEqual(r[k],v)

    def test_reject_tampering_and_bad_status(self):
        expected, base, labels, original = self.prepared('batch02')
        for key,value in [('assistant_reference_viewed','false'),('assistant_prelabel','apologize'),
                          ('assistant_prelabel_reason','changed'),('label_schema_version','intent-draft-v1'),
                          ('review_batch_id','batch03'),('template_id','T9999'),
                          ('human_label','bad'),('human_note',''),('reviewer_id',''),
                          ('msairs_reference_viewed','yes'),('human_review_status','pending')]:
            with self.subTest(key=key):
                rows=deepcopy(original);rows[0][key]=value;self.write(rows)
                with self.assertRaises(ValueError): validate(self.source,expected,base,labels)
        for rows in [original[:-1], original+[original[0]]]:
            self.write(rows)
            with self.assertRaises(ValueError): validate(self.source,expected,base,labels)

    def test_partial_check_and_cli_no_overwrite(self):
        expected,base,labels,rows=self.prepared('batch01')
        rows[0].update(human_note='',human_review_status='pending')
        self.write(rows)
        self.assertEqual(validate(self.source,expected,base,labels,False)[1]['pending'],1)
        with self.assertRaises(ValueError):validate(self.source,expected,base,labels)
        rows[0].update(human_note='TEST_ONLY',human_review_status='reviewed');self.write(rows)
        output=self.folder/'imported_TEST_ONLY'
        command=[sys.executable,str(ROOT/'scripts/import_assisted_review.py'),'--batch','batch01','--input',str(self.source),'--output-dir',str(output)]
        first=subprocess.run(command,capture_output=True)
        self.assertEqual(first.returncode,0,first.stderr)
        saved=(output/'reviewed_batch.csv').read_bytes()
        self.assertEqual(len(read_rows(output/'reviewed_batch.csv')),24)
        self.assertEqual((output/'original_export.csv').read_bytes(),self.source.read_bytes())
        self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
        self.assertEqual(saved,(output/'reviewed_batch.csv').read_bytes())


if __name__=='__main__':unittest.main()
