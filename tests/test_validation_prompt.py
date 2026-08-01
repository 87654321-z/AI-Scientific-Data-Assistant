"""Validation Prompt 最小测试。"""

import unittest

from core.schemas import ColumnInfo, DataRow, ExperimentResult, SourceFile
from prompts.validation_prompt import build_validation_prompt, build_validation_snapshot


def make_result() -> ExperimentResult:
    return ExperimentResult(
        source_files=[SourceFile("test.jpg", "image/jpeg", b"private-image")],
        raw_text="不应发送的原始文本",
        columns=[ColumnInfo("measurement", "测量值", "mg", False, "original")],
        rows=[DataRow(
            values={"measurement": "用户最终值"},
            field_sources={"measurement": "user_modified"},
            observed_values={"measurement": "0.0?"},
        )],
        ai_suggested_rows=[],
        uncertain_items=[],
        warnings=[],
        provider="test",
        model_response_logs=[{"content": "不应发送的日志"}],
    )


class ValidationPromptTests(unittest.TestCase):
    def test_snapshot_uses_observed_values_only(self):
        snapshot = build_validation_snapshot(make_result())
        self.assertEqual(snapshot["observed_rows"][0]["values"]["measurement"], "0.0?")
        self.assertNotIn("raw_text", snapshot)
        self.assertNotIn("model_response_logs", snapshot)

    def test_prompt_is_compact_and_read_only(self):
        prompt = build_validation_prompt(make_result())
        self.assertIn("不得修改、删除、合并", prompt)
        self.assertIn("输入是 Extraction 阶段", prompt)
        self.assertIn("不要重新识别图片", prompt)
        self.assertIn("只允许包含 warnings、suggestions 和 uncertain_items", prompt)
        self.assertIn("suggestions", prompt)
        self.assertNotIn("不应发送的原始文本", prompt)
        self.assertNotIn("private-image", prompt)
        self.assertNotIn("用户最终值", prompt)


if __name__ == "__main__":
    unittest.main()
