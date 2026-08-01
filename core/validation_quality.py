"""为 Validation 结果生成只读的用户展示版本。"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal

from core.validation_schemas import ValidationFinding, ValidationResult


FindingCategory = Literal["suggestion", "uncertain_item"]


@dataclass
class SuppressedFinding:
    """未进入主展示列表、但仍然保留的 finding。"""

    finding: ValidationFinding
    category: FindingCategory
    reason: Literal["duplicate", "medium_limit", "low_limit"]


@dataclass
class ValidationDisplayResult:
    """Quality Filter 产生的只读展示结果。"""

    warnings: list[str] = field(default_factory=list)
    suggestions: list[ValidationFinding] = field(default_factory=list)
    uncertain_items: list[ValidationFinding] = field(default_factory=list)
    suppressed_findings: list[SuppressedFinding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


@dataclass
class _TaggedFinding:
    finding: ValidationFinding
    category: FindingCategory


_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
_LOCATION_RANK = {
    "resolved": 0,
    "recovered": 1,
    "global": 2,
    "unvalidated": 3,
    "ambiguous": 4,
    "unresolved": 5,
}


def build_validation_display_result(
    validation_result: ValidationResult,
    *,
    medium_limit: int = 8,
    low_limit: int = 4,
) -> ValidationDisplayResult:
    """去重、排序和限量，同时保证输入 ValidationResult 不被修改。"""
    if medium_limit < 0 or low_limit < 0:
        raise ValueError("finding 数量限制不能小于 0。")

    tagged = [
        *(
            _TaggedFinding(deepcopy(finding), "suggestion")
            for finding in validation_result.suggestions
        ),
        *(
            _TaggedFinding(deepcopy(finding), "uncertain_item")
            for finding in validation_result.uncertain_items
        ),
    ]
    for item in tagged:
        _normalize_display_fields(item.finding)

    tagged.sort(key=_sort_key)
    unique, duplicates = _deduplicate(tagged)
    retained, limited = _apply_limits(unique, medium_limit, low_limit)
    retained.sort(key=_sort_key)

    suggestions = [
        item.finding for item in retained if item.category == "suggestion"
    ]
    uncertain_items = [
        item.finding for item in retained if item.category == "uncertain_item"
    ]
    suppressed = [
        *(
            SuppressedFinding(item.finding, item.category, "duplicate")
            for item in duplicates
        ),
        *limited,
    ]
    unresolved_count = sum(
        item.finding.location_status in {"ambiguous", "unresolved"}
        for item in retained
    )
    return ValidationDisplayResult(
        warnings=_deduplicate_warnings(validation_result.warnings),
        suggestions=suggestions,
        uncertain_items=uncertain_items,
        suppressed_findings=suppressed,
        summary={
            "raw_finding_count": len(tagged),
            "deduplicated_finding_count": len(unique),
            "displayed_finding_count": len(retained),
            "duplicate_count": len(duplicates),
            "limited_count": len(limited),
            "unresolved_location_count": unresolved_count,
        },
    )


def _normalize_display_fields(finding: ValidationFinding) -> None:
    if finding.severity not in _SEVERITY_RANK:
        finding.severity = "medium"
    if finding.confidence not in _CONFIDENCE_RANK:
        finding.confidence = "low"
    if finding.location_status not in _LOCATION_RANK:
        finding.location_status = "unvalidated"

    if finding.scope == "global":
        finding.location_status = "global"
    elif finding.scope == "cell" and (
        finding.row_index is None or not finding.column_name
    ):
        finding.location_status = "unresolved"
    elif finding.scope == "row" and finding.row_index is None:
        finding.location_status = "unresolved"
    elif finding.scope == "column" and not finding.column_name:
        finding.location_status = "unresolved"


def _deduplicate(
    findings: list[_TaggedFinding],
) -> tuple[list[_TaggedFinding], list[_TaggedFinding]]:
    unique: list[_TaggedFinding] = []
    duplicates: list[_TaggedFinding] = []
    seen: set[tuple[object, ...]] = set()
    for item in findings:
        key = _deduplication_key(item.finding)
        if key in seen:
            duplicates.append(item)
            continue
        seen.add(key)
        unique.append(item)
    return unique, duplicates


def _deduplication_key(finding: ValidationFinding) -> tuple[object, ...]:
    if finding.scope == "cell":
        return (
            "cell",
            finding.issue_type,
            finding.row_index,
            finding.column_name,
            _normalized_text(finding.observed_value),
        )
    return (
        finding.scope,
        finding.issue_type,
        finding.column_name,
        _normalized_text(finding.reason),
    )


def _apply_limits(
    findings: list[_TaggedFinding],
    medium_limit: int,
    low_limit: int,
) -> tuple[list[_TaggedFinding], list[SuppressedFinding]]:
    retained: list[_TaggedFinding] = []
    limited: list[SuppressedFinding] = []
    medium_count = 0
    low_count = 0
    for item in findings:
        severity = item.finding.severity
        if severity == "high":
            retained.append(item)
        elif severity == "medium" and medium_count < medium_limit:
            retained.append(item)
            medium_count += 1
        elif severity == "low" and low_count < low_limit:
            retained.append(item)
            low_count += 1
        else:
            reason = "medium_limit" if severity == "medium" else "low_limit"
            limited.append(SuppressedFinding(item.finding, item.category, reason))
    return retained, limited


def _sort_key(item: _TaggedFinding) -> tuple[object, ...]:
    finding = item.finding
    return (
        _SEVERITY_RANK[finding.severity],
        _LOCATION_RANK[finding.location_status],
        _CONFIDENCE_RANK[finding.confidence],
        finding.row_index if finding.row_index is not None else float("inf"),
        finding.column_name or "",
        finding.finding_id,
    )


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _deduplicate_warnings(warnings: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        key = _normalized_text(warning)
        if key in seen:
            continue
        seen.add(key)
        result.append(warning)
    return result
