"""不联网的 Validation 模拟提供商。"""

from core.schemas import ExperimentResult
from core.validation_schemas import ValidationFinding, ValidationResult
from providers.base_validation_provider import ValidationProvider


class MockValidationProvider(ValidationProvider):
    """使用简单确定性规则生成测试结果，不推测实验数值。"""

    name = "mock_validation"

    def validate_result(
        self,
        experiment_result: ExperimentResult,
        experiment_context: str | None = None,
    ) -> ValidationResult:
        del experiment_context
        uncertain_items: list[ValidationFinding] = []
        finding_number = 1

        for row_index, row in enumerate(experiment_result.rows, start=1):
            observed_values = row.observed_values or row.values
            for column_name, value in observed_values.items():
                issue_type = None
                reason = None
                if value is None or (isinstance(value, str) and not value.strip()):
                    issue_type = "missing_value"
                    reason = "该字段缺少观察值，请人工检查。"
                elif isinstance(value, str) and (
                    "?" in value or "[模糊字符]" in value
                ):
                    issue_type = "unresolved_character"
                    reason = "该字段包含无法确认的字符，请人工检查。"

                if issue_type is None:
                    continue
                uncertain_items.append(ValidationFinding(
                    finding_id=f"mock-validation-{finding_number:04d}",
                    scope="cell",
                    row_index=row_index,
                    column_name=column_name,
                    observed_value=value,
                    issue_type=issue_type,
                    reason=reason,
                    suggested_value=None,
                    confidence="low",
                ))
                finding_number += 1

        warnings = []
        if not experiment_result.rows:
            warnings.append("当前没有可供检查的数据行。")
        return ValidationResult(
            warnings=warnings,
            suggestions=[],
            uncertain_items=uncertain_items,
            provider=self.name,
            status="completed",
            response_metadata={"mode": "offline_mock"},
        )
