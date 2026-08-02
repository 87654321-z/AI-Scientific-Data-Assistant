"""Validation Service 与 Extraction 兼容性测试。"""

import inspect
import unittest
from copy import deepcopy

from core.experiment_parser import process_experiment_images
from core.schemas import ColumnInfo, DataRow, ExperimentResult, SourceFile
from core.validation_service import _normalize_findings, validate_experiment_result
from core.validation_schemas import ValidationFinding, ValidationResult
from providers.doubao_provider import DoubaoProvider


def make_result() -> ExperimentResult:
    return ExperimentResult(
        source_files=[SourceFile("test.jpg", "image/jpeg", b"image")],
        raw_text="",
        columns=[
            ColumnInfo("treatment_id", "处理编号", None, False, "original"),
            ColumnInfo("measurement", "测量值", "mg", False, "original"),
        ],
        rows=[
            DataRow(
                values={"treatment_id": "S0/L/E+/N1", "measurement": "4.58"},
                field_sources={"treatment_id": "original", "measurement": "original"},
                observed_values={"treatment_id": "S0/L/E+/N1", "measurement": "4.58"},
            ),
            DataRow(
                values={"treatment_id": "S0/AH/E+/N2", "measurement": "0.0?"},
                field_sources={"treatment_id": "original", "measurement": "original"},
                observed_values={"treatment_id": "S0/AH/E+/N2", "measurement": "0.0?"},
            ),
            DataRow(
                values={"treatment_id": "S0/H/E+/N3", "measurement": None},
                field_sources={"treatment_id": "original", "measurement": "original"},
                observed_values={"treatment_id": "S0/H/E+/N3", "measurement": None},
            ),
        ],
        ai_suggested_rows=[],
        uncertain_items=[],
        warnings=[],
        provider="extraction_test",
    )


class ValidationServiceTests(unittest.TestCase):
    def test_old_validation_result_constructor_remains_compatible(self):
        finding = ValidationFinding(
            "legacy-1",
            "cell",
            1,
            "measurement",
            "4.58",
            "other",
            "旧结果",
        )
        result = ValidationResult([], [], [finding], "legacy", "completed", {})

        self.assertEqual(finding.confidence, "low")
        self.assertEqual(finding.severity, "medium")
        self.assertEqual(finding.location_status, "unvalidated")
        self.assertIsNone(result.run_log)

    def test_mock_validation_does_not_modify_extraction_result(self):
        experiment_result = make_result()
        original = deepcopy(experiment_result)
        validation = validate_experiment_result(experiment_result, "mock")

        self.assertEqual(experiment_result, original)
        self.assertEqual(validation.provider, "mock_validation")
        self.assertEqual(len(validation.suggestions), 0)
        self.assertEqual(len(validation.uncertain_items), 2)
        self.assertEqual(
            {item.issue_type for item in validation.uncertain_items},
            {"missing_value", "unresolved_character"},
        )

    def test_extraction_default_stage_is_unchanged(self):
        signature = inspect.signature(DoubaoProvider.process_images)
        self.assertEqual(signature.parameters["stage"].default, "extraction")

    def test_existing_extraction_entry_still_runs_without_validation(self):
        result = process_experiment_images(
            [SourceFile("test.jpg", "image/jpeg", b"image")],
            "mock",
        )
        self.assertEqual(result.provider, "mock_vision")
        self.assertEqual(len(result.rows), 1)

    def test_finding_without_location_becomes_warning(self):
        """缺少行列位置的 finding 不进入 Review 来源，但必须保留人工提醒。"""
        finding = ValidationFinding(
            finding_id="missing-location",
            scope="cell",
            row_index=None,
            column_name=None,
            observed_value="0.0?",
            issue_type="unresolved_character",
            reason="无法定位",
            location_status="unknown",
        )
        validation = ValidationResult(uncertain_items=[finding])

        normalized = _normalize_findings(validation, make_result())

        self.assertEqual(normalized.uncertain_items, [])
        self.assertTrue(any("missing-location" in warning for warning in normalized.warnings))

    def test_finding_with_row_and_internal_column_remains_actionable(self):
        """具有有效行号和内部字段名的 finding 应保留给 Review。"""
        finding = ValidationFinding(
            finding_id="located-cell",
            scope="cell",
            row_index=2,
            column_name="measurement",
            observed_value="模型可能返回的改写值",
            issue_type="unresolved_character",
            reason="末位字符不清晰",
            suggested_value="0.01",
            confidence="low",
            location_status="resolved",
        )
        validation = ValidationResult(suggestions=[finding])

        normalized = _normalize_findings(validation, make_result())

        self.assertEqual(len(normalized.suggestions), 1)
        self.assertEqual(normalized.suggestions[0].finding_id, "located-cell")
        self.assertEqual(normalized.suggestions[0].row_index, 2)
        self.assertEqual(normalized.suggestions[0].column_name, "measurement")
        self.assertEqual(normalized.suggestions[0].observed_value, "0.0?")


if __name__ == "__main__":
    unittest.main()
