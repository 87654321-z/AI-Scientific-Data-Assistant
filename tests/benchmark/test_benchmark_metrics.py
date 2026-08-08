"""基准工具的离线指标测试，不调用任何真实 API。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
MODULE_PATH = Path(__file__).with_name("run_benchmark.py")
SPEC = importlib.util.spec_from_file_location("benchmark_runner", MODULE_PATH)
benchmark_runner = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark_runner)

from core.schemas import ColumnInfo, DataRow, ExperimentResult


def make_result(values: dict[str, object], *, replicate_index: int | None = None) -> ExperimentResult:
    return ExperimentResult(
        source_files=[], raw_text="", provider="mock", ai_suggested_rows=[],
        uncertain_items=[], warnings=[],
        columns=[ColumnInfo(name, name, None, False, "original") for name in values],
        rows=[DataRow(values=values, field_sources={}, replicate_index=replicate_index)],
    )


class BenchmarkMetricsTests(unittest.TestCase):
    def test_identifier_anomaly_is_reported_without_modifying_value(self):
        result = make_result({"treatment_id": "S6/LIE+IN1"})
        anomalies = benchmark_runner.identifier_symbol_anomalies(result)
        self.assertEqual(anomalies[0]["value"], "S6/LIE+IN1")
        self.assertIn("merged_identifier_fragments", anomalies[0]["patterns"])

    def test_replicate_summary_detects_compressed_measurements(self):
        result = make_result({"first_measurements": "4.58,4.51,4.51"})
        summary = benchmark_runner.replicate_summary(result)
        self.assertEqual(summary["plural_measurement_fields"], ["first_measurements"])
        self.assertEqual(summary["compressed_values"][0]["kind"], "comma_text")

    def test_numeric_letter_error_is_reported(self):
        result = make_result({"measurement_value": "U.532"})
        errors = benchmark_runner.numeric_letter_errors(result)
        self.assertEqual(errors, [{"row": 1, "field": "measurement_value", "value": "U.532"}])

    def test_identifier_field_summary_records_missing_identifiers(self):
        result = make_result({"measurement_value": "0.532"})
        self.assertEqual(
            benchmark_runner.identifier_field_summary(result),
            {"treatment_id_rows": 0, "sample_id_rows": 0, "missing_identifier_rows": 1},
        )

    def test_build_summary_calculates_rates_and_averages(self):
        report = {
            "images": [
                {
                    "extraction": {
                        "success": True, "api_seconds": 2.0, "row_count": 3,
                        "visual_fields": ["left"], "treatment_id_split_rows": [],
                        "identifier_symbol_anomalies": [{"row": 1}],
                        "numeric_letter_errors": [], "replicate": {"compressed_values": []},
                    },
                    "validation": {"success": True},
                    "review": {"validation_review_ready_count": 2},
                    "excel": {"success": True},
                },
                {
                    "extraction": {"success": False},
                    "validation": {"success": False},
                    "review": {},
                    "excel": {"success": False},
                },
            ]
        }
        summary = benchmark_runner.build_summary(report)
        self.assertEqual(summary["total_images"], 2)
        self.assertEqual(summary["extraction_success_rate"], 0.5)
        self.assertEqual(summary["average_extraction_seconds"], 2.0)
        self.assertEqual(summary["field_anomaly_count"], 1)
        self.assertEqual(summary["identifier_symbol_anomaly_count"], 1)


if __name__ == "__main__":
    unittest.main()
