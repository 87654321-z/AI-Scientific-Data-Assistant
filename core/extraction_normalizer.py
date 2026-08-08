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
_MEASUREMENT_ALIASES = {
    "measurement",
    "value",
    "val",
    "val1",
    "value1",
    "variable_value",
    "numeric_value",
    "reading",
    "result",
}
_MEASUREMENT_PREFIX = "measurement_"
_NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)$")
_NUMBER_LIKE_PATTERN = re.compile(r"^(?=.*\d)[0-9UVEO.,+-]+$", re.IGNORECASE)


def normalize_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """复制并轻量规范化 Extraction JSON，不改写任何单元格值或删除行。

    该函数只映射明确字段别名，并把可疑字段/数值写入 warnings。
    原始 ``payload`` 保持不变，调用方可继续通过模型原始响应追溯内容。
    """
    normalized = deepcopy(payload)
    warnings = _normalized_warnings(normalized.get("warnings"))

    measurement_aliases = _measurement_alias_mapping(normalized, warnings)
    normalized["columns"] = _normalize_columns(
        normalized.get("columns"),
        warnings,
        measurement_aliases,
    )
    normalized["observed_rows"] = _normalize_rows(
        normalized.get("observed_rows"),
        warnings,
        measurement_aliases,
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


def _measurement_alias_mapping(payload: dict[str, Any], warnings: list[str]) -> dict[str, str]:
    """安全识别一个可统一的通用测量字段。

    多个数字列可能是不同实验指标，不能把它们都改成同一个字段；此时保持
    原字段并提示人工确认。只处理单个、无 ``measurement_value`` 冲突的通用别名。
    """
    field_names = _payload_field_names(payload)
    candidates = [name for name in field_names if _is_measurement_alias(name)]
    if not candidates:
        return {}

    if "measurement_value" in field_names:
        for name in candidates:
            _append_warning_once(
                warnings,
                f"测量字段别名 {name} 与 measurement_value 同时存在，已保留原字段，请人工确认字段含义。",
            )
        return {}

    if len(candidates) != 1:
        _append_warning_once(
            warnings,
            "检测到多个通用测量字段别名，可能表示不同实验指标，已保留原字段，请人工确认字段含义。",
        )
        return {}

    candidate = candidates[0]
    values = _field_values(payload.get("observed_rows"), candidate)
    if _values_are_mostly_numeric(values):
        return {candidate: "measurement_value"}

    _append_warning_once(
        warnings,
        f"字段 {candidate} 疑似测量值但内容并非主要为数字，已保留原字段，请人工确认。",
    )
    return {}


def _payload_field_names(payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    columns = payload.get("columns")
    if isinstance(columns, list):
        for column in columns:
            if isinstance(column, dict) and isinstance(column.get("internal_name"), str):
                names.add(column["internal_name"])
    rows = payload.get("observed_rows")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                names.update(name for name in row if isinstance(name, str))
    return names


def _is_measurement_alias(field_name: str) -> bool:
    return field_name in _MEASUREMENT_ALIASES or (
        field_name.startswith(_MEASUREMENT_PREFIX)
        and field_name != "measurement_value"
    )


def _field_values(rows: object, field_name: str) -> list[object]:
    if not isinstance(rows, list):
        return []
    return [row[field_name] for row in rows if isinstance(row, dict) and field_name in row]


def _values_are_mostly_numeric(values: list[object]) -> bool:
    nonempty = [value for value in values if value is not None and str(value).strip()]
    if not nonempty:
        return False
    numeric_count = sum(_is_numeric_or_number_like(value) for value in nonempty)
    return numeric_count / len(nonempty) >= 0.8


def _is_numeric_or_number_like(value: object) -> bool:
    """只用于判断字段语义；U.532 仍会作为原始值保留并产生数据 warning。"""
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return bool(
        _NUMBER_PATTERN.fullmatch(stripped)
        or _NUMBER_LIKE_PATTERN.fullmatch(stripped)
    )


def _normalize_columns(
    columns: object,
    warnings: list[str],
    measurement_aliases: dict[str, str],
) -> object:
    if not isinstance(columns, list):
        return columns

    normalized_columns = []
    for column in columns:
        if not isinstance(column, dict):
            normalized_columns.append(column)
            continue
        normalized_column = deepcopy(column)
        original_name = normalized_column.get("internal_name")
        canonical_name = measurement_aliases.get(
            original_name,
            _canonical_field_name(original_name),
        )
        if canonical_name != original_name:
            normalized_column["internal_name"] = canonical_name
        _add_visual_field_warning(canonical_name, warnings)
        normalized_columns.append(normalized_column)
    return normalized_columns


def _normalize_rows(
    rows: object,
    warnings: list[str],
    measurement_aliases: dict[str, str],
) -> object:
    if not isinstance(rows, list):
        return rows

    normalized_rows = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            normalized_rows.append(row)
            continue

        normalized_row: dict[str, Any] = {}
        for field_name, value in row.items():
            canonical_name = measurement_aliases.get(
                field_name,
                _canonical_field_name(field_name),
            )
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
