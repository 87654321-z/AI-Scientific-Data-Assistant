"""把用户编辑后的表格写回统一结果。"""

from dataclasses import replace
from typing import Any

from core.schemas import DataRow, ExperimentResult
from core.numeric_format import format_final_numeric_rows
from core.scientific_notation import (
    is_structured_identifier_field,
    normalize_scientific_identifier_storage,
)


def confirm_experiment_result(
    result: ExperimentResult,
    edited_rows: list[dict[str, Any]],
    confirmed_value_sources: dict[str, str] | None = None,
    source_row_indices: list[int] | None = None,
    ignored_row_indices: set[int] | None = None,
) -> ExperimentResult:
    confirmed_value_sources = confirmed_value_sources or {}
    ignored_row_indices = ignored_row_indices or set()
    source_row_indices = source_row_indices or list(range(len(edited_rows)))
    edited_by_source_index = dict(zip(source_row_indices, edited_rows))
    rows = []
    for row_index, original_row in enumerate(result.rows):
        row = dict(edited_by_source_index.get(row_index, original_row.values))
        field_sources = {}
        for key, value in row.items():
            value_key = f"{row_index}:{key}"
            if value_key in confirmed_value_sources:
                field_sources[key] = confirmed_value_sources[value_key]
            elif original_row is not None and original_row.values.get(key) == value:
                field_sources[key] = original_row.field_sources.get(key, "original")
            else:
                field_sources[key] = "user_modified"
            # 最终值内部使用普通字符串；原始观察值仍单独、原样保存在 observed_values。
            display_name = next(
                (column.display_name for column in result.columns if column.internal_name == key),
                "",
            )
            if field_sources[key] != "original" and is_structured_identifier_field(key, display_name):
                value = normalize_scientific_identifier_storage(value)
            row[key] = value
        rows.append(DataRow(
            values=row,
            field_sources=field_sources,
            observed_values=(dict(original_row.observed_values) if original_row else dict(row)),
            replicate_group=original_row.replicate_group if original_row else None,
            replicate_index=original_row.replicate_index if original_row else None,
            include_in_final=row_index not in ignored_row_indices,
        ))
    # 用户在表格中新增的行没有原图来源，默认作为有效的用户新增数据。
    for new_index, row in enumerate(edited_rows[len(source_row_indices):], start=1):
        rows.append(DataRow(
            values=dict(row),
            field_sources={key: "user_modified" for key in row},
            observed_values={},
            include_in_final=True,
        ))
    formatted_values = format_final_numeric_rows(
        [data_row.values for data_row in rows],
        result.columns,
    )
    for data_row, values in zip(rows, formatted_values):
        data_row.values = values
    return replace(
        result,
        rows=rows,
        user_confirmed=True,
        modification_records=result.modification_records + ["用户在网页中确认或修改了整理后数据。"],
    )
