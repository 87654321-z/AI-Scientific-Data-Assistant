"""Validation Quality Filter 的确定性离线测试。"""

import unittest
from copy import deepcopy

from core.validation_quality import build_validation_display_result
from core.validation_schemas import ValidationFinding, ValidationResult


def finding(
    finding_id: str,
    *,
    severity: str = "medium",
    confidence: str = "low",
    location_status: str = "resolved",
    row_index: int | None = 1,
    column_name: str | None = "measurement",
    issue_type: str = "other",
    observed_value: object = "value",
) -> ValidationFinding:
    return ValidationFinding(
        finding_id=finding_id,
        scope="cell",
        row_index=row_index,
        column_name=column_name,
        observed_value=observed_value,
        issue_type=issue_type,
        reason=f"reason-{finding_id}",
        confidence=confidence,
        severity=severity,
        location_status=location_status,
    )


class ValidationQualityTests(unittest.TestCase):
    def test_findings_are_sorted_by_severity_location_and_confidence(self):
        result = ValidationResult(uncertain_items=[
            finding("low", severity="low", confidence="high", row_index=4),
            finding(
                "medium-unresolved",
                location_status="unresolved",
                row_index=3,
            ),
            finding("high", severity="high", confidence="low", row_index=1),
            finding("medium-resolved", confidence="high", row_index=2),
        ])

        display = build_validation_display_result(result)

        self.assertEqual(
            [item.finding_id for item in display.uncertain_items],
            ["high", "medium-resolved", "medium-unresolved", "low"],
        )

    def test_duplicates_are_suppressed_but_preserved(self):
        first = finding("first", severity="high", confidence="high")
        duplicate = finding("duplicate", severity="medium", confidence="low")
        result = ValidationResult(
            suggestions=[first],
            uncertain_items=[duplicate],
        )

        display = build_validation_display_result(result)

        self.assertEqual([item.finding_id for item in display.suggestions], ["first"])
        self.assertEqual(display.summary["duplicate_count"], 1)
        self.assertEqual(
            display.suppressed_findings[0].finding.finding_id,
            "duplicate",
        )
        self.assertEqual(display.suppressed_findings[0].reason, "duplicate")

    def test_all_medium_and_low_findings_are_retained(self):
        result = ValidationResult(uncertain_items=[
            *[
                finding(f"medium-{index}", row_index=index)
                for index in range(1, 21)
            ],
            *[
                finding(f"low-{index}", severity="low", row_index=index + 100)
                for index in range(1, 21)
            ],
        ])

        display = build_validation_display_result(result)

        self.assertEqual(display.summary["displayed_finding_count"], 40)
        self.assertEqual(len(display.uncertain_items), 40)
        self.assertEqual(display.suppressed_findings, [])
        self.assertNotIn("limited_count", display.summary)

    def test_all_high_findings_are_retained_without_a_global_limit(self):
        result = ValidationResult(uncertain_items=[
            finding(f"high-{index}", severity="high", row_index=index)
            for index in range(1, 31)
        ])

        display = build_validation_display_result(result)

        self.assertEqual(len(display.uncertain_items), 30)
        self.assertEqual(display.summary["displayed_finding_count"], 30)

    def test_unlocated_finding_is_retained_and_marked(self):
        result = ValidationResult(uncertain_items=[finding(
            "unlocated",
            row_index=None,
            column_name=None,
            location_status="unvalidated",
        )])

        display = build_validation_display_result(result)

        self.assertEqual(len(display.uncertain_items), 1)
        self.assertEqual(
            display.uncertain_items[0].location_status,
            "unresolved",
        )
        self.assertEqual(display.summary["unresolved_location_count"], 1)

    def test_original_validation_result_is_not_modified(self):
        result = ValidationResult(
            warnings=["重复提醒", "重复提醒"],
            uncertain_items=[finding(
                "original",
                severity="invalid",
                location_status="invalid",
                row_index=None,
                column_name=None,
            )],
        )
        before = deepcopy(result)

        display = build_validation_display_result(result)

        self.assertEqual(result, before)
        self.assertEqual(result.uncertain_items[0].severity, "invalid")
        self.assertEqual(display.uncertain_items[0].severity, "medium")
        self.assertEqual(display.warnings, ["重复提醒"])

if __name__ == "__main__":
    unittest.main()
