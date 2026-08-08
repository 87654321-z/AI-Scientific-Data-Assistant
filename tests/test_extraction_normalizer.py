"""Extraction Normalizer 的离线确定性测试。"""

import unittest
from copy import deepcopy

from core.extraction_normalizer import normalize_extraction_payload
from core.schemas import SourceFile
from providers.doubao_provider import DoubaoProvider


class ExtractionNormalizerTests(unittest.TestCase):
    def test_explicit_aliases_are_normalized_without_changing_values(self):
        payload = {
            "columns": [
                {"internal_name": "sample_label"},
                {"internal_name": "experiment_id"},
                {"internal_name": "numeric_value"},
            ],
            "observed_rows": [{
                "sample_label": "A-01",
                "experiment_id": "S0/L/E+/N2",
                "numeric_value": "0.532",
            }],
            "warnings": [],
        }

        result = normalize_extraction_payload(payload)

        self.assertEqual(
            [column["internal_name"] for column in result["columns"]],
            ["sample_id", "treatment_id", "measurement_value"],
        )
        self.assertEqual(result["observed_rows"][0]["sample_id"], "A-01")
        self.assertEqual(result["observed_rows"][0]["treatment_id"], "S0/L/E+/N2")
        self.assertEqual(result["observed_rows"][0]["measurement_value"], "0.532")

    def test_all_requested_aliases_are_mapped(self):
        aliases = {
            "sample_identifier": "sample_id",
            "sample_label": "sample_id",
            "sample_name": "sample_id",
            "sample_code": "sample_id",
            "specimen_id": "sample_id",
            "experimental_id": "treatment_id",
            "experiment_id": "treatment_id",
            "experimental_identifier": "treatment_id",
            "treatment_code": "treatment_id",
            "sample_treatment_id": "treatment_id",
        }
        payload = {
            "columns": [{"internal_name": alias} for alias in aliases],
            "observed_rows": [
                {alias: f"value-{index}"}
                for index, alias in enumerate(aliases)
            ],
            "warnings": [],
        }

        normalized = normalize_extraction_payload(payload)

        self.assertEqual(
            [column["internal_name"] for column in normalized["columns"]],
            list(aliases.values()),
        )
        for index, canonical_name in enumerate(aliases.values()):
            self.assertEqual(
                normalized["observed_rows"][index],
                {canonical_name: f"value-{index}"},
            )

    def test_numeric_val1_and_value1_are_normalized(self):
        for alias in ("val1", "value1"):
            with self.subTest(alias=alias):
                payload = {
                    "columns": [{"internal_name": alias}],
                    "observed_rows": [{alias: "0.532"}, {alias: "1.20"}],
                    "warnings": [],
                }

                normalized = normalize_extraction_payload(payload)

                self.assertEqual(
                    normalized["columns"][0]["internal_name"], "measurement_value",
                )
                self.assertEqual(
                    normalized["observed_rows"][0]["measurement_value"], "0.532",
                )

    def test_semantic_or_non_numeric_measurement_alias_is_not_renamed(self):
        payload = {
            "columns": [
                {"internal_name": "variable_name"},
                {"internal_name": "val1"},
            ],
            "observed_rows": [
                {"variable_name": "株高", "val1": "high"},
                {"variable_name": "鲜重", "val1": "low"},
            ],
            "warnings": [],
        }

        normalized = normalize_extraction_payload(payload)

        self.assertEqual(
            [column["internal_name"] for column in normalized["columns"]],
            ["variable_name", "val1"],
        )
        self.assertEqual(normalized["observed_rows"], payload["observed_rows"])
        self.assertIn(
            "字段 val1 疑似测量值但内容并非主要为数字，已保留原字段，请人工确认。",
            normalized["warnings"],
        )

    def test_multiple_numeric_measurement_aliases_are_preserved(self):
        payload = {
            "columns": [
                {"internal_name": "measurement_left"},
                {"internal_name": "measurement_right"},
            ],
            "observed_rows": [{"measurement_left": "0.532", "measurement_right": "1.20"}],
            "warnings": [],
        }

        normalized = normalize_extraction_payload(payload)

        self.assertEqual(
            [column["internal_name"] for column in normalized["columns"]],
            ["measurement_left", "measurement_right"],
        )
        self.assertIn("多个通用测量字段别名", normalized["warnings"][0])

    def test_order_fields_are_not_renamed(self):
        fields = [
            "record_number",
            "record_serial",
            "sequence_number",
            "line_index",
            "row_number",
        ]
        payload = {
            "columns": [{"internal_name": field} for field in fields],
            "observed_rows": [{field: str(index) for index, field in enumerate(fields, start=1)}],
            "warnings": [],
        }

        normalized = normalize_extraction_payload(payload)

        self.assertEqual(
            [column["internal_name"] for column in normalized["columns"]],
            fields,
        )
        self.assertEqual(normalized["observed_rows"][0], payload["observed_rows"][0])

    def test_visual_field_is_preserved_and_adds_warning(self):
        payload = {
            "columns": [{"internal_name": "column_label"}],
            "observed_rows": [{"column_label": "左侧"}],
            "warnings": [],
        }

        result = normalize_extraction_payload(payload)

        self.assertEqual(result["columns"][0]["internal_name"], "column_label")
        self.assertEqual(result["observed_rows"][0]["column_label"], "左侧")
        self.assertIn("疑似视觉布局字段 column_label，请人工确认字段含义。", result["warnings"])

    def test_letter_in_measurement_is_preserved_and_adds_warning(self):
        payload = {
            "columns": [{"internal_name": "measurement_value"}],
            "observed_rows": [{"measurement_value": "U.532"}],
            "warnings": [],
        }

        result = normalize_extraction_payload(payload)

        self.assertEqual(result["observed_rows"][0]["measurement_value"], "U.532")
        self.assertIn(
            "第1行 measurement_value 含非数字字符，已保留原始值，请人工确认。",
            result["warnings"],
        )

    def test_normal_measurement_does_not_add_warning(self):
        payload = {
            "columns": [{"internal_name": "measurement_value"}],
            "observed_rows": [{"measurement_value": "0.532"}],
            "warnings": [],
        }

        result = normalize_extraction_payload(payload)

        self.assertEqual(result["warnings"], [])

    def test_original_payload_is_not_mutated_or_data_removed(self):
        payload = {
            "columns": [
                {"internal_name": "experimental_id"},
                {"internal_name": "column_label"},
            ],
            "observed_rows": [
                {"experimental_id": "S0/L/E+/N2", "column_label": "A", "measurement": "0.532"},
                {"experimental_id": "S1/H/E-/N1", "measurement": "U.532"},
            ],
            "warnings": ["模型原始警告"],
            "extra_field": {"kept": True},
        }
        original = deepcopy(payload)

        result = normalize_extraction_payload(payload)

        self.assertEqual(payload, original)
        self.assertEqual(len(result["observed_rows"]), 2)
        self.assertEqual(result["extra_field"], {"kept": True})
        self.assertEqual(result["observed_rows"][0]["treatment_id"], "S0/L/E+/N2")
        self.assertEqual(result["observed_rows"][0]["measurement_value"], "0.532")

    def test_provider_applies_normalizer_only_for_extraction_parse(self):
        content = (
            '{"columns":[{"internal_name":"experimental_id"}],'
            '"observed_rows":[{"experimental_id":"S0/L/E+/N2"}],'
            '"warnings":[]}'
        )
        images = [SourceFile("record.jpg", "image/jpeg", b"image-bytes")]
        provider = DoubaoProvider()

        extraction_result = provider._to_experiment_result(
            content,
            images,
            normalize_extraction=True,
        )
        legacy_result = provider._to_experiment_result(content, images)

        self.assertEqual(extraction_result.columns[0].internal_name, "treatment_id")
        self.assertEqual(extraction_result.rows[0].values["treatment_id"], "S0/L/E+/N2")
        self.assertEqual(legacy_result.columns[0].internal_name, "experimental_id")
        self.assertEqual(legacy_result.rows[0].values["experimental_id"], "S0/L/E+/N2")


if __name__ == "__main__":
    unittest.main()
