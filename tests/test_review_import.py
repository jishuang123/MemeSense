"""复核导入的来源一致性、状态规则与输出保护测试。"""

import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memesense.data.review_import import INDEX_FIELDS, REVIEW_FIELDS, validate_review, save_reviewed_index


class ReviewImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "outputs")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.root / "baseline.csv"
        self.source = self.root / "review.csv"
        self.rows = [{"sample_id": f"M{i:04d}", "original_filename": f"{i}.png",
                      "image_path": f"{i}.png", "width": "20", "height": "20", "file_size": "100",
                      "phash": "0123456789abcdef", "template_id": "T0001", "ocr_text": "",
                      "source": "unknown", "notes": '中文,引号"\n换行'} for i in (1, 2)]
        self.base_fields = INDEX_FIELDS + ["notes"]
        self.fields = self.base_fields + REVIEW_FIELDS
        self.write(self.baseline, self.base_fields, self.rows)
        self.review = [{**row, "review_original_template_id": "T0001", "review_status": "correct"}
                       for row in self.rows]
        self.review[1]["template_id"] = "T0002"

    def write(self, path, fields, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def validate(self, complete=True):
        self.write(self.source, self.fields, self.review)
        return validate_review(self.source, self.baseline, complete)

    def test_valid_import_preserves_extra_fields_and_no_overwrite(self):
        fields, rows, counts = self.validate()
        self.assertEqual(counts["correct"], 2)
        output = self.root / "accepted.csv"
        save_reviewed_index(output, fields, rows)
        with output.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(list(csv.DictReader(stream)), self.review)
        before = output.read_bytes()
        with self.assertRaises(FileExistsError):
            save_reviewed_index(output, fields, [])
        self.assertEqual(output.read_bytes(), before)

    def test_unresolved_states_check_only(self):
        self.review[0]["review_status"] = "pending"
        self.review[0]["template_id"] = ""
        self.review[1]["review_status"] = "suspected"
        with self.assertRaisesRegex(ValueError, "复核未完成"):
            self.validate()
        _, _, counts = self.validate(False)
        self.assertEqual(counts, {"correct": 0, "pending": 1, "suspected": 1})

    def test_invalid_id_template_status_and_duplicate(self):
        for field, value in [("sample_id", "M0000"), ("sample_id", "M00001"),
                             ("sample_id", "M0002"), ("template_id", "T0"),
                             ("template_id", ""), ("review_status", "done"),
                             ("review_original_template_id", "T0999")]:
            with self.subTest(field=field, value=value):
                old = self.review[0][field]
                self.review[0][field] = value
                with self.assertRaises(ValueError):
                    self.validate()
                self.review[0][field] = old

    def test_missing_extra_and_mutated_metadata(self):
        for field in ("image_path", "phash", "notes"):
            old = self.review[0][field]
            self.review[0][field] = "changed"
            with self.assertRaisesRegex(ValueError, "原字段"):
                self.validate()
            self.review[0][field] = old
        removed = self.review.pop()
        with self.assertRaisesRegex(ValueError, "遗漏样本"):
            self.validate()
        self.review.append(removed)
        self.review[1]["sample_id"] = "M9999"
        with self.assertRaisesRegex(ValueError, "不在原候选索引"):
            self.validate()

    def test_bad_csv_headers_and_empty(self):
        self.write(self.source, self.fields, [])
        with self.assertRaisesRegex(ValueError, "没有样本"):
            validate_review(self.source, self.baseline)
        self.source.write_text("sample_id,sample_id\nM0001,M0001\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "表头"):
            validate_review(self.source, self.baseline)

    def test_cli_import_and_check_only_preserve_inputs(self):
        self.validate()
        before = (self.source.read_bytes(), self.baseline.read_bytes())
        output = self.root / "reviewed.csv"
        command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/import_reviewed.py"),
                   "--input", str(self.source), "--baseline", str(self.baseline), "--output", str(output)]
        checked = subprocess.run(command + ["--check-only"], capture_output=True)
        self.assertEqual(checked.returncode, 0)
        self.assertFalse(output.exists())
        result = subprocess.run(command, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(command, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        result = subprocess.run(command + ["--output", str(ROOT / "data/raw/forbidden.csv")], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((ROOT / "data/raw/forbidden.csv").exists())
        self.assertEqual((self.source.read_bytes(), self.baseline.read_bytes()), before)


if __name__ == "__main__":
    unittest.main()
