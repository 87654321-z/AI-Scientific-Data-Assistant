"""Mock Validation 页面状态的离线测试。"""

import unittest
from copy import deepcopy

from core.schemas import ColumnInfo, DataRow, ExperimentResult
from core.validation_schemas import ValidationFinding, ValidationResult
from utils.validation_ui import (
    VALIDATION_FAILED,
    VALIDATION_NOT_RUN,
    VALIDATION_SUCCEEDED,
    build_validation_ui_data,
    build_raw_severity_rows,
    clear_validation_state,
    get_validation_status,
    run_validation,
    run_mock_validation,
    summarize_finding_rows,
    validation_state_keys,
)


def make_result() -> ExperimentResult:
    return ExperimentResult(
        source_files=[],
        raw_text="",
        columns=[ColumnInfo("measurement", "测量值", "mg", False, "original")],
        rows=[DataRow(
            values={"measurement": "0.0?"},
            field_sources={"measurement": "original"},
            observed_values={"measurement": "0.0?"},
        )],
        ai_suggested_rows=[],
        uncertain_items=[],
        warnings=[],
        provider="extraction_test",
    )


class ValidationUIStateTests(unittest.TestCase):
    def test_quality_filter_is_used_without_modifying_original_result(self):
        duplicate_a = ValidationFinding(
            "duplicate-a", "cell", 1, "measurement", "0.0?",
            "unresolved_character", "字符模糊", confidence="high",
            severity="high", location_status="resolved",
        )
        duplicate_b = ValidationFinding(
            "duplicate-b", "cell", 1, "measurement", "0.0?",
            "unresolved_character", "重复提醒", confidence="low",
            severity="medium", location_status="resolved",
        )
        original = ValidationResult(
            suggestions=[duplicate_a],
            uncertain_items=[duplicate_b],
        )
        before = deepcopy(original)

        display = build_validation_ui_data(original)

        self.assertEqual(original, before)
        self.assertEqual(display.summary["raw_finding_count"], 2)
        self.assertEqual(display.summary["displayed_finding_count"], 1)
        self.assertEqual(display.summary["duplicate_count"], 1)
        self.assertEqual(display.suggestions[0].severity, "high")

    def test_initial_and_success_states_are_independent(self):
        state = {"doubao_result_image": make_result()}
        extraction_before = deepcopy(state["doubao_result_image"])
        self.assertEqual(get_validation_status(state, "image"), VALIDATION_NOT_RUN)

        succeeded = run_mock_validation(state, state["doubao_result_image"], "image")
        keys = validation_state_keys("image")

        self.assertTrue(succeeded)
        self.assertEqual(state[keys["status"]], VALIDATION_SUCCEEDED)
        self.assertIsInstance(state[keys["result"]], ValidationResult)
        self.assertEqual(state["doubao_result_image"], extraction_before)

    def test_failure_is_downgraded_and_keeps_extraction(self):
        state = {"doubao_result_image": make_result()}
        extraction_before = deepcopy(state["doubao_result_image"])

        def failing_validator(*args, **kwargs):
            raise RuntimeError("模拟 Validation 失败")

        succeeded = run_mock_validation(
            state,
            state["doubao_result_image"],
            "image",
            validator=failing_validator,
        )
        keys = validation_state_keys("image")

        self.assertFalse(succeeded)
        self.assertEqual(state[keys["status"]], VALIDATION_FAILED)
        self.assertIn("模拟 Validation 失败", state[keys["error"]])
        self.assertNotIn(keys["result"], state)
        self.assertEqual(state["doubao_result_image"], extraction_before)

    def test_real_provider_failure_is_downgraded(self):
        state = {"doubao_result_image": make_result()}
        extraction_before = deepcopy(state["doubao_result_image"])
        received_provider = []

        def failing_validator(result, provider_name):
            received_provider.append(provider_name)
            raise RuntimeError("模拟 Doubao API 失败")

        succeeded = run_validation(
            state,
            state["doubao_result_image"],
            "image",
            provider_name="doubao",
            validator=failing_validator,
        )
        keys = validation_state_keys("image")

        self.assertFalse(succeeded)
        self.assertEqual(received_provider, ["doubao"])
        self.assertEqual(state[keys["status"]], VALIDATION_FAILED)
        self.assertIn("模拟 Doubao API 失败", state[keys["error"]])
        self.assertEqual(state["doubao_result_image"], extraction_before)

    def test_real_provider_success_is_saved_separately(self):
        state = {"doubao_result_image": make_result()}
        extraction_before = deepcopy(state["doubao_result_image"])
        received_provider = []

        def successful_validator(result, provider_name):
            received_provider.append(provider_name)
            return ValidationResult(provider="doubao_validation")

        succeeded = run_validation(
            state,
            state["doubao_result_image"],
            "image",
            provider_name="doubao",
            validator=successful_validator,
        )
        keys = validation_state_keys("image")

        self.assertTrue(succeeded)
        self.assertEqual(received_provider, ["doubao"])
        self.assertEqual(state[keys["status"]], VALIDATION_SUCCEEDED)
        self.assertEqual(state[keys["result"]].provider, "doubao_validation")
        self.assertEqual(state["doubao_result_image"], extraction_before)

    def test_clear_state_does_not_remove_extraction(self):
        state = {"doubao_result_image": make_result()}
        run_mock_validation(state, state["doubao_result_image"], "image")
        clear_validation_state(state, "image")

        self.assertEqual(get_validation_status(state, "image"), VALIDATION_NOT_RUN)
        self.assertIn("doubao_result_image", state)

    def test_severity_groups_keep_all_findings_and_summarize_types(self):
        """3 High + 20 Medium + 20 Low 应完整分层，且可按类型汇总。"""
        findings = [
            *[
                ValidationFinding(
                    finding_id=f"high-{index}", scope="cell", row_index=index,
                    column_name="measurement", observed_value=None,
                    issue_type="missing_value", reason="关键值缺失",
                    confidence="high", severity="high", location_status="resolved",
                )
                for index in range(1, 4)
            ],
            *[
                ValidationFinding(
                    finding_id=f"medium-{index}", scope="cell", row_index=index,
                    column_name="treatment_id", observed_value="S0/L1E+1N2",
                    issue_type="identifier_structure_check", reason="编号结构可疑",
                    confidence="medium", severity="medium", location_status="resolved",
                )
                for index in range(1, 21)
            ],
            *[
                ValidationFinding(
                    finding_id=f"low-{index}", scope="cell", row_index=index,
                    column_name="measurement", observed_value="0.?",
                    issue_type="unresolved_character", reason="字符模糊",
                    confidence="low", severity="low", location_status="resolved",
                )
                for index in range(1, 21)
            ],
        ]
        validation = ValidationResult(uncertain_items=findings)

        grouped = build_raw_severity_rows(validation)
        summary = summarize_finding_rows(grouped["medium"])

        self.assertEqual(len(grouped["high"]), 3)
        self.assertEqual(len(grouped["medium"]), 20)
        self.assertEqual(len(grouped["low"]), 20)
        self.assertEqual(summary, [{"问题类型": "实验编号结构可疑", "影响位置数": 20}])
        self.assertEqual(len(validation.uncertain_items), 43)

    def test_49_identifier_findings_are_one_display_type_without_deletion(self):
        findings = [
            ValidationFinding(
                finding_id=f"identifier-{index}", scope="cell", row_index=index,
                column_name="treatment_id", observed_value="S0/L1E+1N2",
                issue_type="identifier_structure_check", reason="编号结构可疑",
                confidence="medium", severity="medium", location_status="resolved",
            )
            for index in range(1, 50)
        ]
        validation = ValidationResult(uncertain_items=findings)

        grouped = build_raw_severity_rows(validation)
        summary = summarize_finding_rows(grouped["medium"])

        self.assertEqual(len(grouped["medium"]), 49)
        self.assertEqual(summary, [{"问题类型": "实验编号结构可疑", "影响位置数": 49}])
        self.assertEqual(len(validation.uncertain_items), 49)


if __name__ == "__main__":
    unittest.main()
