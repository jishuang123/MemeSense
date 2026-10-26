"""图片索引验收测试，生成图片仅放在临时目录。"""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_data as index


class PrepareDataTests(unittest.TestCase):
    def test_cli_incremental_index_and_raw_unchanged(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            base = Path(directory)
            raw = base / "images"
            raw.mkdir()
            output = base / "meme_index.csv"
            for name in ("a.jpg", "b.jpeg", "c.PNG", "d.webp"):
                Image.new("RGB", (30, 20), "red").save(raw / name)
            (raw / "broken.png").write_bytes(b"not an image")
            Image.new("RGB", (10, 10)).save(raw / "ignored.gif")
            before = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                      for p in raw.iterdir()}

            def run():
                result = subprocess.run(
                    [sys.executable, "-X", "utf8", str(ROOT / "scripts/prepare_data.py"),
                     "--input", str(raw), "--output", str(output)],
                    capture_output=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("WARNING", result.stderr)
                return index.load_existing_index(output)

            first = run()
            self.assertEqual([r["sample_id"] for r in first], [f"M{i:04d}" for i in range(1, 5)])
            self.assertTrue(all(len(r["phash"]) == 16 for r in first))
            self.assertTrue(all(r["width"] == "30" and r["height"] == "20" for r in first))
            self.assertTrue(all(r["source"] == "unknown" and not r["ocr_text"] for r in first))
            self.assertEqual(first, run())
            first[0].update(template_id="T001", ocr_text="人工文字", source="manual")
            index.save_index(output, first)
            # 新图排序在旧图之前，也不能改变已有编号。
            Image.new("RGB", (8, 9), "blue").save(raw / "0_new.png")
            updated = run()
            self.assertEqual(updated[:4], first)
            self.assertEqual(updated[-1]["sample_id"], "M0005")
            self.assertEqual(updated[-1]["image_path"], "0_new.png")
            for name, snapshot in before.items():
                path = raw / name
                self.assertEqual((hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns), snapshot)

    def test_empty_directory_generates_header(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            root = Path(directory)
            rows = index.build_index(root, [])
            output = root / "empty.csv"
            index.save_index(output, rows)
            self.assertEqual(output.read_text(encoding="utf-8-sig").strip(), ",".join(index.FIELDS))

    def test_invalid_old_index_is_not_replaced(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            path = Path(directory) / "index.csv"
            row = dict.fromkeys(index.FIELDS, "")
            row.update(sample_id="M0001", image_path="a.png")
            index.save_index(path, [row, row])
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                index.load_existing_index(path)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_record_keeps_id_reserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            root = Path(directory)
            Image.new("RGB", (8, 8)).save(root / "new.png")
            old = dict.fromkeys(index.FIELDS, "")
            old.update(sample_id="M0010", image_path="missing.png")
            with self.assertLogs(index.LOGGER, level="WARNING"):
                rows = index.build_index(root, [old])
            self.assertEqual([row["sample_id"] for row in rows], ["M0010", "M0011"])

    def test_cli_rejects_output_inside_input(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as directory:
            output = Path(directory) / "index.csv"
            with patch.object(sys, "argv", ["prepare_data", "--input", directory, "--output", str(output)]):
                with self.assertLogs(index.LOGGER, level="ERROR"):
                    with self.assertRaises(SystemExit):
                        index.main()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
