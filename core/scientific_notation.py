"""科研实验编号的内部保存与显示格式工具。"""

import re


_SUBSCRIPTS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_PLAIN_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPERSCRIPTS = str.maketrans("+-", "⁺⁻")
_PLAIN_SIGNS = str.maketrans("⁺⁻", "+-")


def format_scientific_identifier_display(value):
    """只在显示层把 S2、N3、E+ 渲染为科研习惯的上下标。"""
    if not isinstance(value, str):
        return value

    displayed = re.sub(
        r"(?<![A-Za-z0-9])([SN])(\d+)(?![A-Za-z0-9])",
        lambda match: f"{match.group(1)}{match.group(2).translate(_SUBSCRIPTS)}",
        value,
    )
    return re.sub(r"(?<![A-Za-z0-9])E([+-])(?![A-Za-z0-9])", lambda match: f"E{match.group(1).translate(_SUPERSCRIPTS)}", displayed)


def normalize_scientific_identifier_storage(value):
    """把用户在显示层看到的上下标还原为普通字符串，便于后续计算。"""
    if not isinstance(value, str):
        return value
    return value.translate(_PLAIN_DIGITS).translate(_PLAIN_SIGNS)


def is_structured_identifier_field(internal_name: str, display_name: str = "") -> bool:
    """判断字段是否为不可随意改写结构的实验/处理/样品编号。"""
    name = f"{internal_name} {display_name}".lower()
    hints = ("id", "identifier", "sample", "treatment", "code", "编号", "样品", "处理", "编码")
    return any(hint in name for hint in hints)


def identifier_structure_is_compatible(observed_value, suggested_value) -> bool:
    """建议不得改变编号的分段、顺序或加入括号；未知片段可被替换。"""
    if not isinstance(observed_value, str) or not isinstance(suggested_value, str):
        return True
    observed = normalize_scientific_identifier_storage(observed_value)
    suggested = normalize_scientific_identifier_storage(suggested_value)
    if any(symbol in suggested for symbol in "()（）"):
        return False
    return observed.count("/") == suggested.count("/")


# 向后兼容旧调用：名称仍保留，但它只负责显示，不应用于内部保存。
def normalize_scientific_subscripts(value):
    return format_scientific_identifier_display(value)
