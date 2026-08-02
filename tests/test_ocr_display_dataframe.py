"""OCR 页面数据表显示的最小回归测试。"""

import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.numeric_format import format_final_numeric_rows, normalize_decimal_separator_rows
from core.scientific_notation import (
    format_scientific_identifier_display,
    is_structured_identifier_field,
)
from prompts.extraction_prompt import build_extraction_prompt


def load_build_display_dataframe():
    """只加载页面中的纯数据函数，避免测试时执行 Streamlit 页面。"""
    page_path = PROJECT_ROOT / "pages" / "2_OCR.py"
    source = page_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(page_path))
    function_node = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "build_display_dataframe"
    )
    namespace = {
        "pd": pd,
        "format_final_numeric_rows": format_final_numeric_rows,
        "normalize_decimal_separator_rows": normalize_decimal_separator_rows,
        "format_scientific_identifier_display": format_scientific_identifier_display,
        "is_structured_identifier_field": is_structured_identifier_field,
    }
    exec(compile(ast.Module(body=[function_node], type_ignores=[]), str(page_path), "exec"), namespace)
    return namespace["build_display_dataframe"]


def load_page_function(function_name: str, namespace: dict):
    """从 Streamlit 页面中单独加载一个纯函数。"""
    page_path = PROJECT_ROOT / "pages" / "2_OCR.py"
    module = ast.parse(page_path.read_text(encoding="utf-8"), filename=str(page_path))
    function_node = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    exec(compile(ast.Module(body=[function_node], type_ignores=[]), str(page_path), "exec"), namespace)
    return namespace[function_name]


class DisplayDataframeTest(unittest.TestCase):
    def test_existing_sequence_column_is_not_inserted_twice(self):
        """模型已返回“序号”时，页面应复用该列且不抛出重名错误。"""
        build_display_dataframe = load_build_display_dataframe()
        result = SimpleNamespace(
            columns=[SimpleNamespace(internal_name="serial_no", display_name="序号")],
            rows=[
                SimpleNamespace(
                    values={"serial_no": "A-01"},
                    replicate_group=None,
                    replicate_index=None,
                )
            ],
            ai_suggested_rows=[],
        )

        dataframe, _ = build_display_dataframe(result, {}, [])

        self.assertEqual(dataframe.columns.tolist().count("序号"), 1)
        self.assertEqual(dataframe.loc[0, "序号"], "A-01")

    def test_sequence_column_is_added_when_missing(self):
        """模型没有返回“序号”时，仍维持原有的连续序号显示。"""
        build_display_dataframe = load_build_display_dataframe()
        result = SimpleNamespace(
            columns=[SimpleNamespace(internal_name="value", display_name="测量值")],
            rows=[
                SimpleNamespace(values={"value": "1.23"}, replicate_group=None, replicate_index=None)
            ],
            ai_suggested_rows=[],
        )

        dataframe, _ = build_display_dataframe(result, {}, [])

        self.assertEqual(dataframe.columns[0], "序号")
        self.assertEqual(dataframe.loc[0, "序号"], 1)

    def test_extraction_prompt_protects_identifier_symbols(self):
        """Extraction Prompt 应明确保护编号前缀、符号和下标。"""
        prompt = build_extraction_prompt()

        self.assertIn("不得把 N\u2081 识别为 1", prompt)
        self.assertIn("下标数字应尽量按图片中的形式保留", prompt)
        self.assertIn("不得删除或改写 `/`、`-`、`+`", prompt)

    def test_runtime_diagnostics_are_read_only_display_values(self):
        """诊断信息应准确反映固定阶段和当前预处理开关。"""
        build_runtime_diagnostics = load_page_function(
            "build_runtime_diagnostics",
            {
                "get_git_commit_hash": lambda: "abc1234",
                "EXTRACTION_STAGE": "extraction",
            },
        )

        diagnostics = build_runtime_diagnostics(True)

        self.assertEqual(diagnostics["Git commit"], "abc1234")
        self.assertEqual(diagnostics["当前 Provider"], "doubao")
        self.assertEqual(diagnostics["当前 Extraction stage"], "extraction")
        self.assertEqual(diagnostics["大图四栏预处理"], "已开启")

    def test_git_hash_falls_back_to_unknown(self):
        """部署环境无法执行 Git 时不应影响页面。"""
        failing_subprocess = SimpleNamespace(
            run=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("git unavailable")),
            SubprocessError=RuntimeError,
        )
        get_git_commit_hash = load_page_function(
            "get_git_commit_hash",
            {
                "subprocess": failing_subprocess,
                "Path": Path,
                "__file__": str(PROJECT_ROOT / "pages" / "2_OCR.py"),
            },
        )

        self.assertEqual(get_git_commit_hash(), "unknown")


if __name__ == "__main__":
    unittest.main()
