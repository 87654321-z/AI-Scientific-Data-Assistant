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
from core.schemas import UncertainItem
from core.scientific_notation import (
    format_scientific_identifier_display,
    is_structured_identifier_field,
)
from core.validation_schemas import ValidationFinding, ValidationResult
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
    def test_validation_findings_join_review_without_mutating_results(self):
        """Validation 建议和不确定项应进入 Review，且两份原始结果保持不变。"""
        build_unified_review_items = load_page_function(
            "build_unified_review_items",
            {
                "ValidationResult": ValidationResult,
                "UncertainItem": UncertainItem,
            },
        )
        legacy_item = UncertainItem("第1行 编号", "legacy", "旧不确定项")
        experiment_result = SimpleNamespace(uncertain_items=[legacy_item])
        suggestion = ValidationFinding(
            finding_id="suggestion-1",
            scope="cell",
            row_index=2,
            column_name="sample_id",
            observed_value="S2/AH/E+/N3",
            issue_type="identifier_pattern",
            reason="字符组合可疑",
            suggested_value="S2/H/E+/N3",
            confidence="low",
        )
        uncertain = ValidationFinding(
            finding_id="uncertain-1",
            scope="cell",
            row_index=3,
            column_name="value",
            observed_value="0.0?",
            issue_type="unresolved_character",
            reason="末位数字不清晰",
        )
        validation_result = ValidationResult(
            suggestions=[suggestion],
            uncertain_items=[uncertain],
        )

        review_items = build_unified_review_items(experiment_result, validation_result)

        self.assertEqual(len(review_items), 3)
        self.assertIn("suggested_value=S2/H/E+/N3", review_items[1].content)
        self.assertEqual(review_items[2].row_index, 3)
        self.assertEqual(experiment_result.uncertain_items, [legacy_item])
        self.assertEqual(validation_result.suggestions, [suggestion])
        self.assertEqual(validation_result.uncertain_items, [uncertain])

    def test_three_findings_for_one_cell_become_one_review_item(self):
        """同一单元格的三个 finding 应共用一张卡片并保留全部发现和候选。"""
        group_review_candidates = load_page_function("group_review_candidates", {})
        candidates = []
        for index, suggestion in enumerate(("S0/L/E+/N2", "S0/H/E+/N2", "S0/H/E+/N2"), start=1):
            item = UncertainItem(f"第5行 处理名称 {index}", "", f"发现{index}")
            candidates.append(
                (
                    item,
                    {
                        "status": "resolved",
                        "row_index": 4,
                        "column_name": "treatment",
                        "column_index": 1,
                        "field_attribute": None,
                        "original_value": "S0/×L/E+/N2",
                        "suggested_value": suggestion,
                        "basis": f"发现{index}",
                        "confidence": "low",
                    },
                )
            )

        review_items = group_review_candidates(candidates)

        self.assertEqual(len(review_items), 1)
        _, _, binding = review_items[0]
        self.assertEqual(len(binding["related_findings"]), 3)
        self.assertEqual(
            binding["suggested_values"],
            ["S0/L/E+/N2", "S0/H/E+/N2"],
        )
        self.assertIsNone(binding["suggested_value"])

    def test_grouping_does_not_modify_validation_result(self):
        """UI 分组和单元格确认键不会删改原始 Validation findings。"""
        group_review_candidates = load_page_function("group_review_candidates", {})
        findings = [
            ValidationFinding(
                finding_id=f"finding-{index}",
                scope="cell",
                row_index=5,
                column_name="treatment",
                observed_value="S0/×L/E+/N2",
                issue_type="identifier_pattern",
                reason=f"发现{index}",
                suggested_value="S0/H/E+/N2",
            )
            for index in range(1, 4)
        ]
        validation_result = ValidationResult(suggestions=findings)
        candidates = [
            (
                UncertainItem(f"第5行 处理名称 {index}", "", finding.reason),
                {
                    "status": "resolved",
                    "row_index": 4,
                    "column_name": "treatment",
                    "column_index": 1,
                    "field_attribute": None,
                    "original_value": finding.observed_value,
                    "suggested_value": finding.suggested_value,
                    "basis": finding.reason,
                    "confidence": finding.confidence,
                },
            )
            for index, finding in enumerate(findings, start=1)
        ]

        review_items = group_review_candidates(candidates)
        confirmation_keys = {
            f"{binding['row_index']}:{binding['column_name']}"
            for _, _, binding in review_items
        }

        self.assertEqual(len(review_items), 1)
        self.assertEqual(confirmation_keys, {"4:treatment"})
        self.assertEqual(validation_result.suggestions, findings)
        self.assertEqual(len(validation_result.suggestions), 3)

    def test_unlocated_validation_finding_does_not_enter_review(self):
        """缺少明确行列的 finding 仍留在 Validation 原结果中，不冒充可确认项。"""
        build_unified_review_items = load_page_function(
            "build_unified_review_items",
            {
                "ValidationResult": ValidationResult,
                "UncertainItem": UncertainItem,
            },
        )
        finding = ValidationFinding(
            finding_id="global-1",
            scope="global",
            row_index=None,
            column_name=None,
            observed_value=None,
            issue_type="other",
            reason="全局提醒",
        )
        validation_result = ValidationResult(warnings=["提醒"], uncertain_items=[finding])

        review_items = build_unified_review_items(
            SimpleNamespace(uncertain_items=[]), validation_result
        )

        self.assertEqual(review_items, [])
        self.assertEqual(validation_result.uncertain_items, [finding])

    def test_replicate_display_uses_group_and_local_sequence(self):
        """模型即使返回 11/12/13，显示层也应展示同组的第1/2/3次。"""
        build_display_dataframe = load_build_display_dataframe()
        result = SimpleNamespace(
            columns=[SimpleNamespace(internal_name="treatment", display_name="处理名称")],
            rows=[
                SimpleNamespace(
                    values={"treatment": "S2/L/E+/N1"},
                    replicate_group="S2/L/E+/N1",
                    replicate_index=index,
                )
                for index in (11, 12, 13)
            ],
            ai_suggested_rows=[],
        )

        dataframe, _ = build_display_dataframe(result, {}, [])

        self.assertEqual(
            dataframe["重复编号"].tolist(),
            ["重复组1·第1次", "重复组1·第2次", "重复组1·第3次"],
        )

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
                "get_ai_model_config": lambda: SimpleNamespace(
                    model="doubao-test-model",
                    api_key="must-not-be-displayed",
                ),
                "EXTRACTION_STAGE": "extraction",
            },
        )

        diagnostics = build_runtime_diagnostics(True)

        self.assertEqual(diagnostics["Git commit"], "abc1234")
        self.assertEqual(diagnostics["当前 Provider"], "doubao")
        self.assertEqual(diagnostics["当前 Extraction stage"], "extraction")
        self.assertEqual(diagnostics["当前模型 ID"], "doubao-test-model")
        self.assertEqual(diagnostics["大图四栏预处理"], "已开启")
        self.assertNotIn("API Key", diagnostics)
        self.assertNotIn("must-not-be-displayed", diagnostics.values())

    def test_runtime_diagnostics_show_unconfigured_model(self):
        """未配置模型时只显示状态，不影响页面。"""
        build_runtime_diagnostics = load_page_function(
            "build_runtime_diagnostics",
            {
                "get_git_commit_hash": lambda: "abc1234",
                "get_ai_model_config": lambda: SimpleNamespace(model=None),
                "EXTRACTION_STAGE": "extraction",
            },
        )

        diagnostics = build_runtime_diagnostics(False)

        self.assertEqual(diagnostics["当前模型 ID"], "未配置")
        self.assertEqual(diagnostics["大图四栏预处理"], "未开启")

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
