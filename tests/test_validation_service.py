"""Validation Service 与 Extraction 兼容性测试。"""

import inspect
import unittest
from copy import deepcopy

from core.experiment_parser import process_experiment_images
from core.schemas import ColumnInfo, DataRow, ExperimentResult, SourceFile
from core.validation_service import validate_experiment_result
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


if __name__ == "__main__":
    unittest.main()
