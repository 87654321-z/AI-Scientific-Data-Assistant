"""Doubao Extraction 只读调试日志测试。"""

import os
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from providers.doubao_provider import DoubaoProvider


class DoubaoExtractionDebugTest(unittest.TestCase):
    def test_debug_switch_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(DoubaoProvider._debug_diagnostics_enabled())

    def test_json_top_level_fields(self):
        content = '{"columns": [], "observed_rows": [], "warnings": []}'

        self.assertEqual(
            DoubaoProvider._json_top_level_fields(content),
            "columns, observed_rows, warnings",
        )
        self.assertEqual(DoubaoProvider._json_top_level_fields('{"columns": ['), "unavailable")

    def test_response_log_contains_safe_debug_metadata(self):
        diagnostics = {
            "model": "doubao-test-model",
            "base_url": "https://example.test/v1",
            "prompt_hash": "abc123",
            "prompt_length": "1234",
            "image_size_bytes": "5678",
            "messages_count": "1",
            "raw_response_summary": '{"columns":[]}',
            "json_top_level_fields": "columns, observed_rows",
        }

        log = DoubaoProvider._response_log("阶段1实验数据提取", '{"columns":[]}', diagnostics)

        self.assertEqual(log["model"], "doubao-test-model")
        self.assertEqual(log["base_url"], "https://example.test/v1")
        self.assertEqual(log["prompt_hash"], "abc123")
        self.assertEqual(log["prompt_length"], "1234")
        self.assertEqual(log["image_size_bytes"], "5678")
        self.assertEqual(log["messages_count"], "1")
        self.assertNotIn("api_key", log)
        self.assertNotIn("ARK_API_KEY", str(log))

    def test_request_diagnostics_are_reproducible_and_safe(self):
        prompt = "只返回结构化实验数据"

        diagnostics = DoubaoProvider._request_diagnostics(
            "doubao-test-model",
            "https://example.test/v1",
            prompt,
            b"image-bytes",
        )

        self.assertEqual(
            diagnostics["prompt_hash"],
            hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(diagnostics["prompt_length"], str(len(prompt)))
        self.assertEqual(diagnostics["image_size_bytes"], str(len(b"image-bytes")))
        self.assertEqual(diagnostics["base_url"], "https://example.test/v1")
        self.assertEqual(diagnostics["messages_count"], "1")
        self.assertNotIn("api_key", diagnostics)


if __name__ == "__main__":
    unittest.main()
