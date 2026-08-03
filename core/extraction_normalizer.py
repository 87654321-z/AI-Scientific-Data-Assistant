"""Extraction JSON 的确定性、低风险规范化。"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


# 仅映射含义明确的模型字段别名；不处理图片顺序字段，避免误改真实实验字段。
_FIELD_ALIASES = {
    "experimental_id": "treatment_id",
    "experiment_id": "treatment_id",
    "experimental_identifier": "treatment_id",
    "treatment_code": "treatment_id",
    "sample_identifier": "sample_id",
    "sample_label": "sample_id",
    "sample_name": "sample_id",
    "sample_code": "sample_id",
    "specimen_id": "sample_id",
    "sample_treatment_id": "treatment_id",
    "measurement": "measurement_value",
    "value": "measurement_value",
    "val": "measurement_value",
    "reading": "measurement_value",
    "result": "measurement_value",
    "numeric_value": "measurement_value",
}

_VISUAL_LAYOUT_FIELDS = {
    "col1",
    "col2",
    "column1",
    "column_label",
    "column_group",
    "left",
    "right",
    "middle",
    "layout_column",
}

_MEASUREMENT_LETTERS = re.compile(r"[UVEO]", re.IGNORECASE)


def normalize_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """复制并轻量规范化 Extraction JSON，不改写任何单元格值或删除行。

    该函数只映射明确字段别名，并把可疑字段/数值写入 warnings。
    原始 ``payload`` 保持不变，调用方可继续通过模型原始响应追溯内容。
    """
    normalized = deepcopy(payload)
    warnings = _normalized_warnings(normalized.get("warnings"))

    normalized["columns"] = _normalize_columns(normalized.get("columns"), warnings)
    normalized["observed_rows"] = _normalize_rows(
        normalized.get("observed_rows"),
        warnings,
    )
    normalized["warnings"] = warnings
    return normalized


def _normalized_warnings(warnings: object) -> list[str]:
    """以列表形式保留模型原有 warnings，忽略非字符串异常项。"""
    if not isinstance(warnings, list):
        return []
    return [warning for warning in warnings if isinstance(warning, str)]


def _canonical_field_name(field_name: object) -> object:
    if not isinstance(field_name, str):
        return field_name
    return _FIELD_ALIASES.get(field_name, field_name)


def _normalize_columns(columns: object, warnings: list[str]) -> object:
    if not isinstance(columns, list):
        return columns

    normalized_columns = []
    for column in columns:
        if not isinstance(column, dict):
            normalized_columns.append(column)
            continue
        normalized_column = deepcopy(column)
        original_name = normalized_column.get("internal_name")
        canonical_name = _canonical_field_name(original_name)
        if canonical_name != original_name:
            normalized_column["internal_name"] = canonical_name
        _add_visual_field_warning(canonical_name, warnings)
        normalized_columns.append(normalized_column)
    return normalized_columns


def _normalize_rows(rows: object, warnings: list[str]) -> object:
    if not isinstance(rows, list):
        return rows

    normalized_rows = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            normalized_rows.append(row)
            continue

        normalized_row: dict[str, Any] = {}
        for field_name, value in row.items():
            canonical_name = _canonical_field_name(field_name)
            # 已存在规范字段时保留该字段，避免别名覆盖真实模型输出。
            if canonical_name in normalized_row and canonical_name != field_name:
                normalized_row[field_name] = value
                continue
            normalized_row[canonical_name] = value
            _add_visual_field_warning(canonical_name, warnings)
            if canonical_name == "measurement_value" and _has_invalid_measurement_letters(value):
                _append_warning_once(
                    warnings,
                    f"第{row_index}行 measurement_value 含非数字字符，已保留原始值，请人工确认。",
                )
        normalized_rows.append(normalized_row)
    return normalized_rows


def _add_visual_field_warning(field_name: object, warnings: list[str]) -> None:
    if isinstance(field_name, str) and field_name.lower() in _VISUAL_LAYOUT_FIELDS:
        _append_warning_once(
            warnings,
            f"疑似视觉布局字段 {field_name}，请人工确认字段含义。",
        )


def _has_invalid_measurement_letters(value: object) -> bool:
    return isinstance(value, str) and bool(_MEASUREMENT_LETTERS.search(value))


def _append_warning_once(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)
