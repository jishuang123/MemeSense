"""验证数据流程中会影响实验正确性和原图安全的行为。"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memesense.data.annotation import validate_annotations, write_jsonl
from memesense.data.deduplicate import scan_images
from memesense.data.split import split_records
from memesense.bot.qq_bot import GroupContext


class DataTests(unittest.TestCase):
    def test_scan_preserves_files_and_detects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a.png", "b.png"):
                (root / name).write_bytes(b"same-image-bytes")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            rows = scan_images(root)
            self.assertEqual(rows[1]["duplicate_of"], "a.png")
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_split_no_duplicate_leakage_and_reproducible(self):
        rows = [{"sha256": str(i // 2), "image_path": str(i)} for i in range(40)]
        result = split_records(rows)
        self.assertEqual(result, split_records(rows))
        groups = [{r["sha256"] for r in part} for part in result.values()]
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertEqual(sum(map(len, result.values())), len(rows))

    def test_invalid_ratios(self):
        with self.assertRaises(ValueError):
            split_records([], (0.8, 0.2, 0.2))

    def test_conflicting_labels_rejected(self):
        rows = [{"image_path": f"{i}.png", "sha256": "a" * 64, "text": "", "label": label}
                for i, label in enumerate(("happy", "sad"))]
        with self.assertRaises(ValueError):
            validate_annotations(rows, ["happy", "sad"])

    def test_output_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.jsonl"
            write_jsonl(path, [{"label": "happy"}])
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_jsonl(path, [])
            self.assertEqual(path.read_bytes(), before)

    def test_group_context_isolation_and_bounds(self):
        context = GroupContext(max_messages=2, max_chars=3)
        for text in ("first", "second", "third"):
            context.add("a", "alice", text, "2026-10-15")
        context.add("b", "bob", "other", "2026-10-15")
        self.assertEqual([m.text for m in context.get("a")], ["sec", "thi"])
        context.reset("a")
        self.assertEqual(context.get("a"), ())
        self.assertEqual(context.get("b")[0].text, "oth")


if __name__ == "__main__":
    unittest.main()
