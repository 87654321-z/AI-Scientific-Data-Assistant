"""平台无关的 Validation 主流程。"""

from copy import deepcopy
import re

from core.schemas import ExperimentResult
from core.validation_schemas import ValidationFinding, ValidationResult
from providers.validation_provider_factory import create_validation_provider


def validate_experiment_result(
    experiment_result: ExperimentResult,
    provider_name: str,
    experiment_context: str | None = None,
) -> ValidationResult:
    """检查 Extraction 结果，同时保证原对象不被 Provider 修改。"""
    before_validation = _protected_data_snapshot(experiment_result)
    provider = create_validation_provider(provider_name)
    validation_result = provider.validate_result(
        experiment_result,
        experiment_context,
    )
    if _protected_data_snapshot(experiment_result) != before_validation:
        raise RuntimeError("Validation Provider 修改了只读的 Extraction 数据。")
    _append_local_quality_findings(validation_result, experiment_result)
    return _normalize_findings(validation_result, experiment_result)


def _protected_data_snapshot(experiment_result: ExperimentResult):
    return deepcopy((
        experiment_result.columns,
        experiment_result.rows,
        experiment_result.ai_suggested_rows,
        experiment_result.uncertain_items,
        experiment_result.warnings,
        experiment_result.user_confirmed,
        experiment_result.modification_records,
    ))


def _normalize_findings(
    validation_result: ValidationResult,
    experiment_result: ExperimentResult,
) -> ValidationResult:
    valid_columns = {column.internal_name for column in experiment_result.columns}
    row_count = len(experiment_result.rows)
    warnings = list(validation_result.warnings)
    used_ids: set[str] = set()

    def normalize_list(findings: list[ValidationFinding]) -> list[ValidationFinding]:
        normalized = []
        for finding in findings:
            _calibrate_finding_classification(finding)
            if not _has_valid_binding(finding, row_count, valid_columns):
                warnings.append(
                    f"校验项 {finding.finding_id} 无法定位到有效行列，请人工检查。"
                )
                continue
            finding.finding_id = _unique_finding_id(finding.finding_id, used_ids)
            if finding.scope == "cell":
                row = experiment_result.rows[finding.row_index - 1]
                observed_values = row.observed_values or row.values
                finding.observed_value = observed_values.get(finding.column_name)
            normalized.append(finding)
        return normalized

    validation_result.suggestions = normalize_list(validation_result.suggestions)
    validation_result.uncertain_items = normalize_list(validation_result.uncertain_items)
    validation_result.warnings = warnings
    return validation_result


_CLASSIFICATION_LEVELS = {"low", "medium", "high"}
_HEURISTIC_FINDING_TYPES = {
    "identifier_pattern",
    "identifier_structure_check",
    "compressed_repeat_measurement_check",
    "possible_outlier",
}


def _calibrate_finding_classification(finding: ValidationFinding) -> None:
    """区分问题影响程度与判断把握度，并约束仅凭结构推断的发现。"""
    if finding.severity not in _CLASSIFICATION_LEVELS:
        finding.severity = "medium"
    if finding.confidence not in _CLASSIFICATION_LEVELS:
        finding.confidence = "low"

    # Validation 只读取 Extraction 文本，不查看原图。这些启发式类型可以较有
    # 把握地指出“值得检查”，但不能高置信度断定原图字符或正确替代值。
    if finding.issue_type in _HEURISTIC_FINDING_TYPES:
        if finding.severity == "high":
            finding.severity = "medium"
        if finding.confidence == "high":
            finding.confidence = "medium"


_IDENTIFIER_FIELD_PATTERN = re.compile(
    r"(?:treatment|sample|experiment|identifier|processing|process|code)",
    re.IGNORECASE,
)
_MEASUREMENT_FIELD_PATTERN = re.compile(
    r"(?:measurement|measure|value|val|reading|result|numeric)",
    re.IGNORECASE,
)
_NUMBER_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])[+-]?(?:\d+(?:[.]\d+)?|[.]\d+)(?![A-Za-z0-9_])")


def _append_local_quality_findings(
    validation_result: ValidationResult,
    experiment_result: ExperimentResult,
) -> None:
    """Add deterministic, non-destructive validation findings.

    These checks deliberately report only suspicious patterns.  They never
    rewrite an observed value or provide a guessed replacement.
    """
    findings = validation_result.uncertain_items
    finding_number = 1

    for row_index, row in enumerate(experiment_result.rows, start=1):
        observed_values = row.observed_values or row.values
        for column_name, value in observed_values.items():
            if not isinstance(value, str) or not value.strip():
                continue

            if _is_identifier_field(column_name) and _has_identifier_structure_issue(value):
                findings.append(ValidationFinding(
                    finding_id=f"local-identifier-structure-{finding_number:04d}",
                    scope="cell",
                    row_index=row_index,
                    column_name=column_name,
                    observed_value=value,
                    issue_type="identifier_structure_check",
                    reason="实验编号疑似存在分隔符缺失、竖线替代斜杠或片段粘连，请人工确认。",
                    suggested_value=None,
                    confidence="medium",
                    severity="medium",
                    location_status="resolved",
                ))
                finding_number += 1

            if _is_measurement_field(column_name) and _has_compressed_measurements(value):
                findings.append(ValidationFinding(
                    finding_id=f"local-compressed-repeat-{finding_number:04d}",
                    scope="cell",
                    row_index=row_index,
                    column_name=column_name,
                    observed_value=value,
                    issue_type="compressed_repeat_measurement_check",
                    reason="检测到疑似多个重复测量值被压缩在同一单元格，请人工确认。",
                    suggested_value=None,
                    confidence="medium",
                    severity="medium",
                    location_status="resolved",
                ))
                finding_number += 1


def _is_identifier_field(column_name: str) -> bool:
    return bool(_IDENTIFIER_FIELD_PATTERN.search(column_name))


def _is_measurement_field(column_name: str) -> bool:
    return bool(_MEASUREMENT_FIELD_PATTERN.search(column_name))


def _has_identifier_structure_issue(value: str) -> bool:
    """Return true only for common, suspicious identifier-shape anomalies."""
    compact = value.strip()
    return any((
        "|" in compact,
        # Match a missing slash before N even when a handwritten/truncated
        # identifier ends at N (for example ``E+1N`` or ``E-IN``).
        bool(re.search(r"E[+-][1Il]?N(?:\d|$)", compact)),
        bool(re.search(r"(?:^|/)[^/]*[1Il]E[+-]", compact)),
        bool(re.search(r"/[1Il](?=(?:/|E[+-]|N\d|$))", compact)),
    ))


def _has_compressed_measurements(value: str) -> bool:
    """Detect multiple numeric tokens in one measurement cell without splitting."""
    return len(_NUMBER_TOKEN_PATTERN.findall(value)) >= 2


def _has_valid_binding(
    finding: ValidationFinding,
    row_count: int,
    valid_columns: set[str],
) -> bool:
    if finding.scope == "global":
        return True
    if finding.scope == "column":
        return finding.column_name in valid_columns
    if finding.scope == "row":
        return finding.row_index is not None and 1 <= finding.row_index <= row_count
    return (
        finding.scope == "cell"
        and finding.row_index is not None
        and 1 <= finding.row_index <= row_count
        and finding.column_name in valid_columns
    )


def _unique_finding_id(finding_id: str, used_ids: set[str]) -> str:
    base_id = finding_id or "validation-finding"
    candidate = base_id
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate
