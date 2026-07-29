"""最终确认科研数值的显示与导出格式化工具。"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any


_NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_COMMA_DECIMAL_PATTERN = re.compile(r"^([+-]?\d+),(\d+)$")
_IDENTIFIER_HINTS = (
    "id", "sample", "treatment", "group", "replicate", "code",
    "编号", "样品", "处理", "重复", "编码",
)


def is_numeric_experiment_field(internal_name: str, display_name: str, values: list[Any]) -> bool:
    """判断字段是否更像测量数值而不是样品或处理标识。"""
    field_text = f"{internal_name} {display_name}".lower()
    if any(hint in field_text for hint in _IDENTIFIER_HINTS):
        return False
    visible_values = [value for value in values if value is not None and str(value).strip() != ""]
    return bool(visible_values) and all(_NUMBER_PATTERN.fullmatch(str(value).strip()) for value in visible_values)


def normalize_decimal_separator_value(value: Any) -> Any:
    """把完整的欧洲小数写法 4,58 转成 4.58；不处理其他文本。"""
    if not isinstance(value, str):
        return value
    match = _COMMA_DECIMAL_PATTERN.fullmatch(value.strip())
    return f"{match.group(1)}.{match.group(2)}" if match else value


def normalize_decimal_separator_rows(rows: list[dict[str, Any]], columns) -> list[dict[str, Any]]:
    """只规范化非编号字段中的完整逗号小数，返回副本而不改写原始识别行。"""
    normalized_rows = [dict(row) for row in rows]
    for column in columns:
        field_text = f"{column.internal_name} {column.display_name}".lower()
        if any(hint in field_text for hint in _IDENTIFIER_HINTS):
            continue
        for row in normalized_rows:
            row[column.internal_name] = normalize_decimal_separator_value(
                row.get(column.internal_name)
            )
    return normalized_rows


def format_numeric_value(value: Any) -> Any:
    """将可识别的普通十进制数值显示为两位小数。"""
    if value is None or not _NUMBER_PATTERN.fullmatch(str(value).strip()):
        return value
    try:
        return format(Decimal(str(value).strip()), ".2f")
    except InvalidOperation:
        return value


def format_final_numeric_rows(rows: list[dict[str, Any]], columns) -> list[dict[str, Any]]:
    """返回两位小数的最终数据副本，不修改调用方的原始行对象。"""
    formatted_rows = normalize_decimal_separator_rows(rows, columns)
    for column in columns:
        values = [row.get(column.internal_name) for row in formatted_rows]
        if not is_numeric_experiment_field(column.internal_name, column.display_name, values):
            continue
        for row in formatted_rows:
            row[column.internal_name] = format_numeric_value(row.get(column.internal_name))
    return formatted_rows
