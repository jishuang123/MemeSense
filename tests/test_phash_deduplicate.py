"""验证近重复分组、边界阈值和 CSV 读写保护。"""

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memesense.data.deduplicate import group_by_phash


def sample(number: int, phash: str) -> dict[str, str]:
    return {"sample_id": f"M{number:04d}", "original_filename": f"{number}.png",
            "image_path": f"{number}.png", "width": "32", "height": "32",
            "file_size": "100", "phash": phash, "template_id": "manual",
            "ocr_text": "保留人工文字", "source": "unknown"}


class PhashTests(unittest.TestCase):
    def test_threshold_transitive_groups_and_singleton(self):
        rows = [sample(1, "0000000000000000"), sample(2, "0000000000000001"),
                sample(3, "0000000000000003"), sample(4, "ffffffffffffffff")]
        grouped, pairs = group_by_phash(rows, 1)
        self.assertEqual([r["template_id"] for r in grouped], ["T0001"] * 3 + ["T0004"])
        self.assertEqual([(r["sample_id_a"], r["sample_id_b"]) for r in pairs],
                         [("M0001", "M0002"), ("M0002", "M0003")])
        self.assertTrue(all(r["distance"] == "1" for r in pairs))
        self.assertTrue(all(r["template_id"] == "manual" for r in rows))
        reversed_result, _ = group_by_phash(list(reversed(rows)), 1)
        self.assertEqual({r["sample_id"]: r["template_id"] for r in grouped},
                         {r["sample_id"]: r["template_id"] for r in reversed_result})

    def test_zero_threshold_invalid_hash_and_empty(self):
        rows = [sample(1, "abcdef0123456789"), sample(2, "ABCDEF0123456789"), sample(3, "bad")]
        with self.assertLogs("memesense.data.deduplicate", level="WARNING"):
            grouped, pairs = group_by_phash(rows, 0)
        self.assertEqual([r["template_id"] for r in grouped], ["T0001", "T0001", ""])
        self.assertEqual(pairs[0]["distance"], "0")
        self.assertEqual(group_by_phash([], 6), ([], []))
        for threshold in (-1, 65):
            with self.assertRaises(ValueError):
                group_by_phash([], threshold)

    def test_cli_repeatable_input_preserved_and_collision_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            base = Path(directory)
            source, output, pairs = (base / name for name in ("index.csv", "grouped.csv", "pairs.csv"))
            rows = [sample(1, "0000000000000000"), sample(2, "0000000000000001")]
            rows[0]["notes"] = "人工复核列"
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            original = source.read_bytes()
            command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/deduplicate.py"),
                       "--input", str(source), "--output", str(output), "--pairs", str(pairs)]
            for _ in range(2):
                result = subprocess.run(command, capture_output=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(source.read_bytes(), original)
                with output.open(encoding="utf-8-sig", newline="") as stream:
                    grouped = list(csv.DictReader(stream))
                self.assertEqual([r["template_id"] for r in grouped], ["T0001", "T0001"])
                self.assertEqual(grouped[0]["notes"], "人工复核列")
                self.assertEqual(grouped[0]["ocr_text"], rows[0]["ocr_text"])
            result = subprocess.run(command + ["--output", str(source)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
