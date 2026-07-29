"""局部识别结果的临时合并工具。"""

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from core.schemas import DataRow


_ROW_NUMBER_FIELDS = ("row_number", "left_num", "id", "sample_id", "number")
_OBSERVED_VALUE_FIELDS = ("observed_value", "right_val", "value", "measurement_value")


def _sample_id_sort_key(row: Mapping[str, Any]) -> tuple[int, int | str]:
    """已知数字编号按数值排序；无法转换的编号稳定排在末尾。"""
    try:
        return 0, int(row.get("sample_id"))
    except (TypeError, ValueError):
        return 1, str(row.get("sample_id", ""))


def merge_region_rows(
    region_results: Mapping[str, Iterable[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """合并多个局部区域的 rows，并按 sample_id 排序。

    不去重、不补值、不修改原始行；重复编号和空值都会保留给后续人工确认。
    """
    merged_rows: list[dict[str, Any]] = []
    for rows in region_results.values():
        for row in rows:
            merged_rows.append(deepcopy(dict(row)))
    return sorted(merged_rows, key=_sample_id_sort_key)


def _first_present_value(
    values: Mapping[str, Any],
    field_names: tuple[str, ...],
) -> tuple[str | None, Any]:
    """按既定优先级返回第一个实际存在的字段和值。"""
    for field_name in field_names:
        if field_name in values:
            return field_name, values[field_name]
    return None, None


def normalize_region_data_row(row: DataRow) -> DataRow:
    """将局部识别行统一为 row_number 与 observed_value 两个字段。

    不补值、不排序；编号存在而测量值为空时，仍保留该行。
    """
    row_field, row_number = _first_present_value(row.values, _ROW_NUMBER_FIELDS)
    value_field, observed_value = _first_present_value(row.values, _OBSERVED_VALUE_FIELDS)
    observed_row_field, observed_row_number = _first_present_value(
        row.observed_values,
        _ROW_NUMBER_FIELDS,
    )
    observed_value_field, original_observed_value = _first_present_value(
        row.observed_values,
        _OBSERVED_VALUE_FIELDS,
    )

    return DataRow(
        values={"row_number": row_number, "observed_value": observed_value},
        field_sources={
            "row_number": row.field_sources.get(row_field or "", "original"),
            "observed_value": row.field_sources.get(value_field or "", "original"),
        },
        observed_values={
            "row_number": observed_row_number if observed_row_field else row_number,
            "observed_value": (
                original_observed_value if observed_value_field else observed_value
            ),
        },
        replicate_group=row.replicate_group,
        replicate_index=row.replicate_index,
        include_in_final=row.include_in_final,
    )


def merge_region_data_rows(region_rows: Mapping[str, Iterable[DataRow]]) -> list[DataRow]:
    """按区域传入顺序合并局部行，并在合并前完成字段标准化。"""
    merged_rows: list[DataRow] = []
    for rows in region_rows.values():
        merged_rows.extend(normalize_region_data_row(row) for row in rows)
    return merged_rows
