"""数据集清单和离线质量检查工具测试，不访问网络。"""

import sys
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.benchmark.datasets.inspect_dataset import inspect_entries, render_markdown


class DatasetToolsTests(unittest.TestCase):
    def test_generated_manifest_has_required_schema_and_one_hundred_entries(self):
        manifest_path = PROJECT_ROOT / "tests/benchmark/datasets/images_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["images"]
        self.assertEqual(len(entries), 100)
        for key in ("image_path", "source_url", "source_type", "license", "category", "notes"):
            self.assertTrue(all(key in entry for entry in entries), key)

    def test_quality_summary_counts_manifest_without_images(self):
        entries = [{
            "image_path": "tests/benchmark/datasets/images/missing.jpg",
            "source_type": "huggingface_dataset",
            "license": "Apache-2.0",
            "category": "printed_table",
        }]
        summary = inspect_entries(entries)
        self.assertEqual(summary["manifest_entries"], 1)
        self.assertEqual(summary["downloaded_images"], 0)
        self.assertEqual(summary["missing_images"], 1)

    def test_quality_summary_detects_local_image(self):
        relative_path = Path("tests/benchmark/datasets/images/test_quality_image.png")
        path = PROJECT_ROOT / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            Image.new("RGB", (120, 180), "white").save(path)
            summary = inspect_entries([{
                "image_path": relative_path.as_posix(),
                "source_type": "local_test",
                "license": "test-only",
                "category": "printed_table",
            }])
            self.assertEqual(summary["downloaded_images"], 1)
            self.assertEqual(summary["corrupt_images"], [])
            self.assertIn("分类统计", render_markdown(summary))
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
