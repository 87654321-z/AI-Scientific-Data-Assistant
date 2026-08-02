"""实验记录图片的文字识别和人工校对页面。"""

import difflib
import re
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

from config.ai_model_config import get_ai_model_config
from core.excel_exporter import export_experiment_result_to_excel
from core.experiment_parser import process_experiment_images
from core.numeric_format import (
    format_final_numeric_rows,
    normalize_decimal_separator_rows,
    normalize_decimal_separator_value,
)
from core.preprocessing.layout_detector import detect_large_image_layout
from core.review_service import confirm_experiment_result
from core.schemas import SourceFile
from core.scientific_notation import (
    format_scientific_identifier_display,
    identifier_structure_is_compatible,
    is_structured_identifier_field,
    normalize_scientific_identifier_storage,
)
from prompts.extraction_prompt import EXTRACTION_STAGE
from utils.validation_ui import (
    clear_validation_state,
    render_mock_validation_panel,
    render_validation_panel,
)


def get_git_commit_hash() -> str:
    """只读获取当前 Git 短哈希；部署环境无法读取时返回 unknown。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def build_runtime_diagnostics(enable_preprocessing: bool) -> dict[str, str]:
    """生成只读运行信息，不参与识别参数或结果处理。"""
    model_id = get_ai_model_config().model or "未配置"
    return {
        "Git commit": get_git_commit_hash(),
        "当前 Provider": "doubao",
        "当前 Extraction stage": EXTRACTION_STAGE,
        "当前模型 ID": model_id,
        "大图四栏预处理": "已开启" if enable_preprocessing else "未开启",
    }


@st.cache_resource(show_spinner=False)
def load_ocr_reader():
    """加载并缓存本地 EasyOCR 模型，避免每次点击都重新加载。"""
    import easyocr

    return easyocr.Reader(["ch_sim", "en"], gpu=False)


def preprocess_image(image: Image.Image) -> Image.Image:
    """使用简单、可见的步骤改善图片清晰度。"""
    corrected_image = ImageOps.exif_transpose(image)
    grayscale_image = ImageOps.grayscale(corrected_image)
    contrast_image = ImageEnhance.Contrast(grayscale_image).enhance(1.8)
    sharpened_image = contrast_image.filter(
        ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3)
    )
    return sharpened_image.convert("RGB")


def recognize_image(reader, image: Image.Image) -> str:
    """识别一张图片，并按 EasyOCR 返回的顺序保留换行。"""
    text_lines = reader.readtext(np.array(image.convert("RGB")), detail=0, paragraph=False)
    return "\n".join(text_lines) or "未识别到文字。"


def parse_uncertain_item(content: str, reason: str) -> dict[str, str | None]:
    """读取提示词写入不确定项中的观察值、建议值和置信度。"""
    observed_match = re.search(r"observed_value=(.*?); suggested_value=", content)
    suggested_match = re.search(r"suggested_value=(.*?); confidence=", content)
    confidence_match = re.search(r"confidence=([^;]+)", content)
    target_type_match = re.search(r"target_type=([^;]+)", content)
    column_name_match = re.search(r"column_name=([^;]+)", content)

    def optional_value(match: re.Match[str] | None) -> str | None:
        if match is None:
            return None
        value = match.group(1).strip()
        return None if value.lower() == "null" else value

    return {
        "observed_value": optional_value(observed_match),
        "suggested_value": optional_value(suggested_match),
        "confidence": optional_value(confidence_match),
        "basis": reason,
        "target_type": optional_value(target_type_match) or "cell",
        "column_name": optional_value(column_name_match),
    }


def format_user_value(value):
    """用户界面统一显示科研编号上下标，内部数据不在这里改写。"""
    if value is None:
        return None
    return format_scientific_identifier_display(normalize_decimal_separator_value(value))


def translate_ai_text(text: str | None) -> str:
    """将常见英文模型提示转为面向科研用户的中文；未知内容仍原样保留。"""
    if not text:
        return "未提供"
    translations = {
        "Several measured values at end of right column are truncated": "右侧末尾的部分测量值可能存在截断，请人工检查。",
        "Several measured values are truncated": "部分测量值可能存在截断，请人工检查。",
        "right column": "右侧列",
        "truncated": "可能存在截断",
        "unclear": "不清晰",
        "unknown": "无法确认",
    }
    translated = str(text)
    for source, target in translations.items():
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)
    # 不把模型的英文说明直接抛给普通用户；定位与原始日志仍可在开发模式追溯。
    if re.search(r"[A-Za-z]{3,}", translated):
        return "AI 提示中包含未能可靠翻译的说明，请结合原始图片人工检查。"
    return translated


def can_apply_ai_suggestion(column_name: str, display_name: str, observed_value, suggested_value) -> bool:
    """结构化编号的 AI 建议必须保持原有分段结构，才可由用户一键采用。"""
    return (
        not is_structured_identifier_field(column_name, display_name)
        or identifier_structure_is_compatible(observed_value, suggested_value)
    )


def find_uncertain_target(location: str, columns) -> tuple[int | None, str | None]:
    """从中英文自然语言位置说明解析可绑定的行列位置。"""
    normalized_location = str(location or "").strip()
    row_match = re.search(
        r"第\s*(\d+)\s*行|(?:line|row)\s*(\d+)|编号\s*(\d+)",
        normalized_location,
        flags=re.IGNORECASE,
    )
    row_number = next((group for group in row_match.groups() if group), None) if row_match else None
    row_index = int(row_number) - 1 if row_number else None
    field_location = re.sub(r"第\s*\d+\s*行|(?:line|row)\s*\d+", "", normalized_location, flags=re.IGNORECASE)
    field_location = re.sub(r"[（(]编号\d+[）)]", "", field_location)
    field_location_lower = field_location.lower()
    column_name = next(
        (
            column.internal_name
            for column in columns
            if (
                (column.display_name and column.display_name.lower() in field_location_lower)
                or column.internal_name.lower() in field_location_lower
            )
        ),
        None,
    )
    if column_name is None:
        fallback_columns = {
            "处理名称": "treatment",
            "处理编号": "treatment",
            "样品编号": "sample_id",
            "编号": "sample_id",
            "Na含量": "na_content",
            "K含量": "k_content",
            "experimental identifier": "exp_id",
            "experiment identifier": "exp_id",
            "exp_id": "exp_id",
            "identifier": "sample_id",
            "left": "sample_id",
        }
        for label, internal_name in fallback_columns.items():
            if label.lower() not in field_location_lower:
                continue
            matching_column = next(
                (column.internal_name for column in columns if column.internal_name == internal_name),
                None,
            )
            if matching_column is not None:
                column_name = matching_column
                break
    return row_index, column_name


def resolve_uncertain_binding(item, details: dict[str, str | None], doubao_result) -> dict[str, object]:
    """为不确定项生成行列绑定；无法绑定时保留为待人工处理状态。"""
    source_row_index = getattr(item, "row_index", None)
    source_column_name = getattr(item, "column_name", None) or details.get("column_name")
    source_column_index = getattr(item, "column_index", None)
    parsed_row_index, parsed_column_name = find_uncertain_target(item.location, doubao_result.columns)

    target_type = details.get("target_type") or "cell"
    declared_column_name = details.get("column_name")
    if target_type in {"field_name", "field_unit"}:
        column = next(
            (
                candidate
                for candidate in doubao_result.columns
                if declared_column_name in {candidate.internal_name, candidate.display_name}
            ),
            None,
        )
        if column is not None:
            attribute = "display_name" if target_type == "field_name" else "unit"
            original_value = details["observed_value"]
            if original_value is None:
                original_value = column.display_name if attribute == "display_name" else column.original_unit
            return {
                "status": "field_resolved",
                "target_type": target_type,
                "field_attribute": attribute,
                "row_index": None,
                "column_index": None,
                "column_name": column.internal_name,
                "original_value": original_value,
                "suggested_value": details["suggested_value"],
                "basis": details["basis"],
                "confidence": details["confidence"],
            }

    def normalize_row_index(value):
        if value is None:
            return None
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            return None
        if numeric_value == 0:
            return 0
        return numeric_value - 1 if numeric_value > 0 else None

    def normalize_column_name(value):
        if value is None:
            return None
        text_value = str(value)
        for column in doubao_result.columns:
            if text_value in {column.internal_name, column.display_name}:
                return column.internal_name
        return None

    def normalize_column_index(value):
        if value is None:
            return None
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            return None
        if numeric_value == 0:
            return 0
        return numeric_value - 1 if 1 <= numeric_value <= len(doubao_result.columns) else None

    row_index = normalize_row_index(source_row_index)
    column_name = normalize_column_name(source_column_name)
    column_index = normalize_column_index(source_column_index)
    if row_index is None:
        row_index = parsed_row_index
    if column_name is None:
        column_name = parsed_column_name
    if column_index is not None and column_name is None:
        column_name = doubao_result.columns[column_index].internal_name
    if column_name is not None and column_index is None:
        column_index = next(
            (index for index, column in enumerate(doubao_result.columns) if column.internal_name == column_name),
            None,
        )
        if column_index is None:
            column_index = len(doubao_result.columns)

    observed_value = details["observed_value"]
    matches = []
    for candidate_row_index, row in enumerate(doubao_result.rows):
        for candidate_column_index, column in enumerate(doubao_result.columns):
            if observed_value and str(row.values.get(column.internal_name, "")) == str(observed_value):
                matches.append((candidate_row_index, candidate_column_index, column.internal_name))

    if row_index is None and len({match[0] for match in matches}) == 1:
        row_index = matches[0][0]
    if column_name is None:
        matching_columns = [match for match in matches if match[0] == row_index]
        if len({match[2] for match in matching_columns}) == 1:
            column_name = matching_columns[0][2]
    if column_name is not None and column_index is None:
        column_index = next(
            (index for index, column in enumerate(doubao_result.columns) if column.internal_name == column_name),
            None,
        )

    return {
        "status": "resolved" if row_index is not None and column_index is not None and column_name is not None else "unresolved",
        "target_type": "cell",
        "field_attribute": None,
        "row_index": row_index,
        "column_index": column_index,
        "column_name": column_name,
        "original_value": observed_value,
        "suggested_value": details["suggested_value"],
        "basis": details["basis"],
        "confidence": details["confidence"],
    }


def build_display_dataframe(
    doubao_result,
    confirmed_values: dict[str, str],
    bindings: list[dict[str, object]],
    format_final_values: bool = False,
    ignored_row_indices: set[int] | None = None,
    include_row_mapping: bool = False,
):
    """保留全部原始行/字段，再叠加原始识别值和最终确认值。"""
    internal_names = [column.internal_name for column in doubao_result.columns]
    display_names = {
        column.internal_name: column.display_name or column.internal_name
        for column in doubao_result.columns
    }
    fallback_display_names = {
        "sample_id": "编号",
        "sample_no": "编号",
        "treatment": "处理名称",
        "treatment_name": "处理名称",
        "na_content": "Na含量",
        "k_content": "K含量",
    }
    for row in [*doubao_result.ai_suggested_rows, *doubao_result.rows]:
        for field_name in row.values:
            if field_name not in internal_names:
                internal_names.append(field_name)
            display_names.setdefault(
                field_name,
                fallback_display_names.get(field_name, f"未命名字段（{field_name}）"),
            )

    row_count = max(len(doubao_result.rows), len(doubao_result.ai_suggested_rows))
    rows = []
    for row_index in range(row_count):
        row_values = {}
        if row_index < len(doubao_result.ai_suggested_rows):
            row_values.update(doubao_result.ai_suggested_rows[row_index].values)
        if row_index < len(doubao_result.rows):
            row_values.update(doubao_result.rows[row_index].values)
        rows.append(row_values)

    for binding in bindings:
        if binding["status"] != "resolved":
            continue
        row_index = binding["row_index"]
        column_name = binding["column_name"]
        if column_name not in internal_names:
            internal_names.append(column_name)
            display_names.setdefault(
                column_name,
                fallback_display_names.get(column_name, f"未命名字段（{column_name}）"),
            )
        while len(rows) <= row_index:
            rows.append({})
        value_key = f"{row_index}:{column_name}"
        if value_key in confirmed_values:
            rows[row_index][column_name] = confirmed_values[value_key]
        elif binding["original_value"] is not None:
            rows[row_index][column_name] = binding["original_value"]

    for value_key, value in confirmed_values.items():
        if value_key.startswith("field:"):
            continue
        row_index_text, column_name = value_key.split(":", maxsplit=1)
        row_index = int(row_index_text)
        while len(rows) <= row_index:
            rows.append({})
        if column_name not in internal_names:
            internal_names.append(column_name)
            display_names.setdefault(
                column_name,
                fallback_display_names.get(column_name, f"未命名字段（{column_name}）"),
            )
        rows[row_index][column_name] = value

    source_row_indices = list(range(len(rows)))
    ignored_row_indices = ignored_row_indices or set()
    active_positions = [
        index
        for index in source_row_indices
        if index not in ignored_row_indices
    ]
    rows = [rows[index] for index in active_positions]
    source_row_indices = active_positions

    # 仅处理显示/确认副本；doubao_result.rows 中的原始观察值不被改写。
    rows = normalize_decimal_separator_rows(rows, doubao_result.columns)
    if format_final_values:
        rows = format_final_numeric_rows(rows, doubao_result.columns)
    # 内部继续保存普通字符串；仅给用户看的副本显示上下标。
    rows = [
        {
            field_name: (
                format_scientific_identifier_display(value)
                if is_structured_identifier_field(field_name, display_names.get(field_name, ""))
                else value
            )
            for field_name, value in row.items()
        }
        for row in rows
    ]
    dataframe = pd.DataFrame(rows).reindex(columns=internal_names)
    dataframe = dataframe.rename(columns=display_names)
    if "序号" not in dataframe.columns:
        dataframe.insert(0, "序号", range(1, len(dataframe) + 1))
    # 重复信息只用于当前页面显示，不写入 treatment 等原始数据字段。
    replicate_labels = []
    for source_row_index in source_row_indices:
        source_row = (
            doubao_result.rows[source_row_index]
            if source_row_index < len(doubao_result.rows)
            else None
        )
        if source_row and source_row.replicate_group and source_row.replicate_index:
            replicate_labels.append(f"重复{source_row.replicate_index}")
        else:
            replicate_labels.append("")
    if any(replicate_labels):
        dataframe.insert(1, "重复编号", replicate_labels)
    dataframe.index = source_row_indices
    dataframe.index.name = "原始行位置"
    if include_row_mapping:
        return dataframe, display_names, source_row_indices
    return dataframe, display_names


def describe_difference(observed_value: str | None, suggested_value: str | None) -> str:
    """用简单中文说明 AI 建议会改动的字符，不影响其他单元格。"""
    if not observed_value or not suggested_value or observed_value == suggested_value:
        return "AI 建议只会更新当前单元格，不会修改其他行或字段。"
    changes = []
    matcher = difflib.SequenceMatcher(None, observed_value, suggested_value)
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation != "equal":
            old_text = observed_value[old_start:old_end] or "无"
            new_text = suggested_value[new_start:new_end] or "无"
            changes.append(f"“{old_text}”改为“{new_text}”")
    return "；".join(changes) or "AI 建议只会更新当前单元格，不会修改其他行或字段。"


def save_confirmation(
    image_id: str,
    item,
    details: dict[str, str | None],
    row_index: int,
    column_name: str,
    final_value: str,
    action: str,
) -> None:
    """保存一个单元格的用户确认值和可追溯记录，然后立即刷新表格。"""
    confirmed_values_key = f"doubao_confirmed_values_{image_id}"
    confirmation_records_key = f"doubao_confirmation_records_{image_id}"
    confirmation_sources_key = f"doubao_confirmation_sources_{image_id}"
    value_key = f"{row_index}:{column_name}"
    confirmed_values = st.session_state.setdefault(confirmed_values_key, {})
    records = st.session_state.setdefault(confirmation_records_key, {})
    sources = st.session_state.setdefault(confirmation_sources_key, {})
    if not isinstance(records, dict):
        records = {}
        st.session_state[confirmation_records_key] = records
    confirmed_values[value_key] = normalize_scientific_identifier_storage(final_value)
    sources[value_key] = {
        "采用 AI 建议": "ai_suggestion",
        "保留原始识别": "user_kept_original",
        "手动修改": "user_modified",
    }.get(action, "user_modified")
    records[value_key] = (
        f"{item.location}：原始观察值={details['observed_value'] or 'null'}；"
        f"AI 建议={details['suggested_value'] or 'null'}；"
        f"用户最终确认值={final_value}；操作={action}；"
        f"依据={translate_ai_text(details['basis'])}；"
        f"置信度={details['confidence'] or '未提供'}。"
    )
    st.session_state.pop(f"doubao_editor_{image_id}", None)
    st.session_state[f"doubao_selected_cell_{image_id}"] = value_key
    st.rerun()


def save_field_confirmation(
    image_id: str,
    item,
    details: dict[str, str | None],
    column_name: str,
    field_attribute: str,
    final_value: str,
    action: str,
) -> None:
    """保存字段名或单位的最终确认值及来源，不把它伪装成普通数据行。"""
    confirmed_values = st.session_state.setdefault(f"doubao_confirmed_values_{image_id}", {})
    records = st.session_state.setdefault(f"doubao_confirmation_records_{image_id}", {})
    sources = st.session_state.setdefault(f"doubao_confirmation_sources_{image_id}", {})
    value_key = f"field:{column_name}:{field_attribute}"
    confirmed_values[value_key] = normalize_scientific_identifier_storage(final_value)
    sources[value_key] = {
        "采用 AI 建议": "ai_suggestion",
        "保留原始识别": "user_kept_original",
        "手动修改": "user_modified",
    }.get(action, "user_modified")
    records[value_key] = (
        f"{item.location}：原始观察值={details['observed_value'] or 'null'}；"
        f"AI 建议={details['suggested_value'] or 'null'}；"
        f"用户最终确认值={final_value}；来源={sources[value_key]}；操作={action}；"
        f"依据={translate_ai_text(details['basis'])}；置信度={details['confidence'] or '未提供'}。"
    )
    st.rerun()


def apply_field_confirmations(doubao_result, confirmed_values: dict[str, str], confirmation_sources: dict[str, str]):
    """把字段名和单位的确认值写入结果副本，供现有 Excel 导出逻辑追踪。"""
    updated_columns = []
    for column in doubao_result.columns:
        name_key = f"field:{column.internal_name}:display_name"
        unit_key = f"field:{column.internal_name}:unit"
        updated_column = column
        if name_key in confirmed_values:
            updated_column = replace(
                updated_column,
                display_name=confirmed_values[name_key],
                source=confirmation_sources.get(name_key, "user_modified"),
            )
        if unit_key in confirmed_values:
            updated_column = replace(
                updated_column,
                unit=confirmed_values[unit_key],
                final_unit=confirmed_values[unit_key],
                source=confirmation_sources.get(unit_key, "user_modified"),
            )
        updated_columns.append(updated_column)
    return replace(doubao_result, columns=updated_columns)


def render_ai_result(doubao_result, image_id: str, timings: dict[str, float]) -> None:
    """展示中文结构化表格、逐项确认和现有 Excel 导出入口。"""
    render_started = time.perf_counter()
    confirmed_values_key = f"doubao_confirmed_values_{image_id}"
    confirmation_records_key = f"doubao_confirmation_records_{image_id}"
    confirmation_sources_key = f"doubao_confirmation_sources_{image_id}"
    ignored_rows_key = f"doubao_ignored_row_indices_{image_id}"
    confirmed_values = st.session_state.setdefault(confirmed_values_key, {})
    confirmation_records = st.session_state.setdefault(confirmation_records_key, {})
    confirmation_sources = st.session_state.setdefault(confirmation_sources_key, {})
    ignored_row_indices = set(st.session_state.setdefault(ignored_rows_key, set()))
    if not isinstance(confirmation_records, dict):
        confirmation_records = {}
        st.session_state[confirmation_records_key] = confirmation_records

    bindings_key = f"doubao_uncertain_bindings_{image_id}"
    bindings = {}
    review_items = []
    for item_number, item in enumerate(doubao_result.uncertain_items, start=1):
        details = parse_uncertain_item(item.content, item.reason)
        binding = resolve_uncertain_binding(item, details, doubao_result)
        bindings[str(item_number)] = binding
        if binding["status"] == "resolved":
            if binding["row_index"] in ignored_row_indices:
                continue
        review_items.append((item_number, item, binding))
    st.session_state[bindings_key] = bindings

    total_uncertain = len(review_items)
    confirmable_keys = {
        (
            f"{binding['row_index']}:{binding['column_name']}"
            if binding["status"] == "resolved"
            else f"field:{binding['column_name']}:{binding['field_attribute']}"
        )
        for _, _, binding in review_items
        if binding["status"] in {"resolved", "field_resolved"}
    }
    confirmed_count = len(confirmable_keys.intersection(confirmed_values))
    unresolved_count = sum(1 for _, _, binding in review_items if binding["status"] == "unresolved")
    all_confirmed = total_uncertain == 0 or (confirmed_count == total_uncertain and unresolved_count == 0)
    table_title = "最终确认数据" if all_confirmed else "当前整理结果"

    st.subheader(table_title)
    progress_column, status_column = st.columns([1, 2])
    with progress_column:
        st.metric("确认进度", f"{confirmed_count} / {total_uncertain}")
    with status_column:
        if all_confirmed:
            st.success("所有不确定项已确认，可以导出 Excel。")
        else:
            st.warning(f"还有 {total_uncertain - confirmed_count} 项需要确认。黄色单元格为待确认位置。")

    display_dataframe, display_names, source_row_indices = build_display_dataframe(
        doubao_result,
        confirmed_values,
        [binding for _, _, binding in review_items],
        format_final_values=all_confirmed,
        ignored_row_indices=ignored_row_indices,
        include_row_mapping=True,
    )
    display_serial_by_source_index = {
        source_index: serial_number
        for serial_number, source_index in enumerate(source_row_indices, start=1)
    }
    selected_cell = st.session_state.get(f"doubao_selected_cell_{image_id}")
    pending_cells = set()
    for _, _, binding in review_items:
        if binding["status"] != "resolved":
            continue
        value_key = f"{binding['row_index']}:{binding['column_name']}"
        if value_key not in confirmed_values:
            pending_cells.add(value_key)

    def highlight_cells(row):
        styles = [""] * len(row)
        for column_index, display_name in enumerate(row.index):
            internal_name = next(
                (key for key, value in display_names.items() if value == display_name),
                None,
            )
            value_key = f"{row.name}:{internal_name}"
            if value_key == selected_cell:
                styles[column_index] = "background-color: #ffd166; font-weight: bold"
            elif value_key in pending_cells:
                styles[column_index] = "background-color: #fff3cd"
        return styles

    st.dataframe(display_dataframe.style.apply(highlight_cells, axis=1), width="stretch", hide_index=True)
    render_validation_panel(doubao_result, image_id, provider_name="doubao")
    with st.expander("查看 AI 原始识别文本", expanded=False):
        st.text(doubao_result.raw_text)
    model_response_logs = getattr(doubao_result, "model_response_logs", [])
    if st.query_params.get("developer") == "true" and model_response_logs:
        with st.expander("开发日志：比较两次模型返回", expanded=False):
            st.caption("仅当前运行可见；不会保存图片或写入项目目录。")
            for log in model_response_logs:
                st.markdown(f"**{log['stage']}**")
                debug_fields = {
                    "模型": log.get("model"),
                    "Prompt 长度": log.get("prompt_length"),
                    "图片大小（bytes）": log.get("image_size_bytes"),
                    "解析前 JSON 顶层字段": log.get("json_top_level_fields"),
                    "原始响应摘要": log.get("raw_response_summary"),
                }
                visible_debug_fields = {
                    label: value for label, value in debug_fields.items() if value is not None
                }
                if visible_debug_fields:
                    st.json(visible_debug_fields)
                st.code(log["content"], language="json")
    with st.expander("查看字段技术信息", expanded=False):
        st.dataframe(pd.DataFrame([
            {"内部字段名": column.internal_name, "显示名称": column.display_name, "单位": column.unit or ""}
            for column in doubao_result.columns
        ]), width="stretch")

    st.subheader("表格中的待确认单元格")
    st.caption("表格中的黄色单元格需要确认。每次操作只更新对应的一个单元格，表格值就是最终导出的 final_value。")
    if not review_items:
        st.success("没有需要确认的不确定项。")
    else:
        for item_number, item, binding in review_items:
            if binding["status"] == "unresolved":
                st.markdown(f"#### {item.location}")
                st.write(f"原始识别值：{format_user_value(binding['original_value']) or '未能确认'}")
                st.write(f"AI 建议值：{format_user_value(binding['suggested_value']) or '没有建议'}")
                st.write(f"最终确认值：{format_user_value(binding['original_value']) or '未能确认'}")
                with st.expander("查看 AI 辅助信息", expanded=False):
                    st.write(f"推测依据：{translate_ai_text(binding['basis'])}")
                    st.write(f"置信度：{binding['confidence'] or '未提供'}")
                st.warning("该不确定项无法自动定位，请手动处理。")
                continue

            if binding["status"] == "field_resolved":
                column_name = binding["column_name"]
                field_attribute = binding["field_attribute"]
                original_value = binding["original_value"]
                suggested_value = binding["suggested_value"]
                field_label = "字段名称" if field_attribute == "display_name" else "单位"
                value_key = f"field:{column_name}:{field_attribute}"
                final_value = confirmed_values.get(value_key, original_value)
                st.markdown(f"#### {display_names.get(column_name, column_name)} · {field_label}")
                information_columns = st.columns(3)
                information_columns[0].markdown(f"**原始识别值**  \n`{format_user_value(original_value) or '未能确认'}`")
                information_columns[1].markdown(f"**AI 建议值**  \n`{format_user_value(suggested_value) or '没有建议'}`")
                information_columns[2].markdown(f"**最终确认值**  \n`{format_user_value(final_value) or '未能确认'}`")
                with st.expander("查看 AI 辅助信息", expanded=False):
                    st.write(f"推测依据：{translate_ai_text(binding['basis'])}")
                    st.write(f"置信度：{binding['confidence'] or '未提供'}")
                field_actions = st.columns(3)
                details = {
                    "observed_value": original_value,
                    "suggested_value": suggested_value,
                    "basis": binding["basis"],
                    "confidence": binding["confidence"],
                }
                with field_actions[0]:
                    if st.button("采用 AI 建议", key=f"field_accept_{image_id}_{item_number}"):
                        if suggested_value:
                            save_field_confirmation(image_id, item, details, column_name, field_attribute, suggested_value, "采用 AI 建议")
                        else:
                            st.error("AI 没有提供可采用的建议。")
                with field_actions[1]:
                    if st.button("保留原始识别", key=f"field_keep_{image_id}_{item_number}"):
                        if original_value:
                            save_field_confirmation(image_id, item, details, column_name, field_attribute, original_value, "保留原始识别")
                        else:
                            st.error("原始识别为空，请手动填写最终值。")
                with field_actions[2]:
                    manual_value = st.text_input("手动修改", value=original_value or "", key=f"field_manual_{image_id}_{item_number}")
                    if st.button("确认手动修改", key=f"field_manual_confirm_{image_id}_{item_number}"):
                        # 空值也是用户明确确认的结果，例如原图该字段本来就应为空。
                        save_field_confirmation(image_id, item, details, column_name, field_attribute, manual_value.strip(), "手动修改")
                continue

            row_index = binding["row_index"]
            column_index = binding["column_index"]
            column_name = binding["column_name"]
            original_value = binding["original_value"]
            suggested_value = binding["suggested_value"]
            field_name = display_names[column_name]
            value_key = f"{row_index}:{column_name}"
            final_value = confirmed_values.get(value_key, original_value)
            display_serial = display_serial_by_source_index.get(row_index)
            position_text = (
                f"序号 {display_serial}（原始第 {row_index + 1} 行）· {field_name} · 第 {column_index + 1} 列"
                if display_serial is not None
                else f"原始第 {row_index + 1} 行 · {field_name} · 第 {column_index + 1} 列"
            )
            st.markdown(f"#### {position_text}")
            information_columns = st.columns(3)
            information_columns[0].markdown(f"**原始识别值**  \n`{format_user_value(original_value) or '未能确认'}`")
            information_columns[1].markdown(f"**AI 建议值**  \n`{format_user_value(suggested_value) or '没有建议'}`")
            information_columns[2].markdown(f"**最终确认值**  \n`{format_user_value(final_value) or '未能确认'}`")
            st.caption(f"建议改动：{describe_difference(original_value, suggested_value)}")
            with st.expander("查看 AI 辅助信息", expanded=False):
                st.write(f"推测依据：{translate_ai_text(binding['basis'])}")
                st.write(f"置信度：{binding['confidence'] or '未提供'}")

            if st.button("定位并高亮", key=f"locate_{image_id}_{item_number}"):
                st.session_state[f"doubao_selected_cell_{image_id}"] = value_key
                st.rerun()
            if value_key in confirmed_values:
                st.success("该单元格已确认，黄色标记已取消。")

            action_columns = st.columns(3)
            with action_columns[0]:
                if st.button("采用 AI 建议", key=f"accept_{image_id}_{item_number}"):
                    if suggested_value:
                        if not can_apply_ai_suggestion(column_name, field_name, original_value, suggested_value):
                            st.warning("安全提醒：AI 建议改变了实验编号结构。该建议不会自动生效；你已点击确认后才会采用。")
                        details = {
                            "observed_value": original_value,
                            "suggested_value": suggested_value,
                            "basis": binding["basis"],
                            "confidence": binding["confidence"],
                        }
                        save_confirmation(image_id, item, details, row_index, column_name, suggested_value, "采用 AI 建议")
                    else:
                        st.error("AI 没有提供可采用的建议。")
            with action_columns[1]:
                if st.button("保留原始识别", key=f"keep_{image_id}_{item_number}"):
                    if original_value:
                        details = {
                            "observed_value": original_value,
                            "suggested_value": suggested_value,
                            "basis": binding["basis"],
                            "confidence": binding["confidence"],
                        }
                        save_confirmation(image_id, item, details, row_index, column_name, original_value, "保留原始识别")
                    else:
                        st.error("原始识别为空，请手动填写最终值。")
            with action_columns[2]:
                manual_value = st.text_input("手动修改", value=original_value or "", key=f"manual_{image_id}_{item_number}")
                if st.button("确认手动修改", key=f"manual_confirm_{image_id}_{item_number}"):
                    # 允许用户明确确认空值；该操作仍会保留原始观察与修改来源。
                    details = {
                        "observed_value": original_value,
                        "suggested_value": suggested_value,
                        "basis": binding["basis"],
                        "confidence": binding["confidence"],
                    }
                    save_confirmation(image_id, item, details, row_index, column_name, manual_value.strip(), "手动修改")

    st.subheader("数据表编辑")
    st.caption("通常只需确认上方不确定项；如需改动其他内容，可在此编辑。")
    with st.expander("无效行处理", expanded=False):
        st.caption("忽略不会删除原始识别记录；被忽略行不会进入最终数据和 Excel 主数据表。")
        if doubao_result.rows:
            selected_source_index = st.selectbox(
                "选择原始数据行",
                options=list(range(len(doubao_result.rows))),
                format_func=lambda index: f"原始第 {index + 1} 行",
                key=f"include_row_select_{image_id}",
            )
            current_decision = "忽略" if selected_source_index in ignored_row_indices else "保留"
            include_decision = st.selectbox(
                "是否纳入最终结果",
                options=["保留", "忽略"],
                index=0 if current_decision == "保留" else 1,
                key=f"include_row_decision_{image_id}",
            )
            if st.button("保存纳入状态", key=f"save_include_row_{image_id}"):
                if include_decision == "忽略":
                    ignored_row_indices.add(selected_source_index)
                    action = "用户选择忽略，不纳入最终结果。"
                    source = "user_ignored"
                else:
                    ignored_row_indices.discard(selected_source_index)
                    action = "用户选择保留，纳入最终结果。"
                    source = "user_kept"
                st.session_state[ignored_rows_key] = ignored_row_indices
                confirmation_records[f"row:{selected_source_index}"] = f"原始第 {selected_source_index + 1} 行：{action}"
                confirmation_sources[f"row:{selected_source_index}"] = source
                st.session_state.pop(f"doubao_editor_{image_id}", None)
                st.rerun()
        else:
            st.info("当前没有可删除的有效数据行。")
    reverse_names = {value: key for key, value in display_names.items()}
    edited_display = st.data_editor(
        display_dataframe,
        num_rows="dynamic",
        key=f"doubao_editor_{image_id}",
        hide_index=True,
    )
    edited_data = (
        edited_display
        .drop(columns=["序号", "重复编号"], errors="ignore")
        .rename(columns=reverse_names)
        .to_dict(orient="records")
    )
    if confirmation_records:
        with st.expander("查看已保存的确认记录", expanded=False):
            for record in confirmation_records.values():
                st.write(f"- {record}")

    if doubao_result.warnings:
        st.write("AI 提示：")
        for warning in doubao_result.warnings:
            st.write(f"- {translate_ai_text(warning)}")

    if st.button("生成 Excel", key=f"export_doubao_{image_id}"):
        import tempfile
        from pathlib import Path

        result_with_confirmation_records = replace(
            apply_field_confirmations(doubao_result, confirmed_values, confirmation_sources),
            modification_records=doubao_result.modification_records + list(confirmation_records.values()),
        )
        row_value_sources = {
            key: value for key, value in confirmation_sources.items() if not key.startswith("field:")
        }
        confirmed_result = confirm_experiment_result(
            result_with_confirmation_records,
            edited_data,
            confirmed_value_sources=row_value_sources,
            source_row_indices=source_row_indices,
            ignored_row_indices=ignored_row_indices,
        )
        with tempfile.TemporaryDirectory() as temporary_folder:
            excel_path = Path(temporary_folder) / "科研数据.xlsx"
            export_experiment_result_to_excel(confirmed_result, str(excel_path))
            st.session_state[f"doubao_excel_{image_id}"] = excel_path.read_bytes()

    excel_key = f"doubao_excel_{image_id}"
    if excel_key in st.session_state:
        st.download_button(
            "下载 Excel",
            data=st.session_state[excel_key],
            file_name="科研数据.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_doubao_{image_id}",
        )

    timings["page_render_seconds"] = time.perf_counter() - render_started
    st.caption(
        "耗时记录："
        f"图片读取 {timings.get('image_read_seconds', 0):.2f} 秒；"
        f"API 调用 {timings.get('api_call_seconds', 0):.2f} 秒；"
        f"模型返回 {timings.get('model_return_seconds', 0):.2f} 秒（含网络请求）；"
        f"页面生成 {timings['page_render_seconds']:.2f} 秒。"
    )


def render_backup_ocr(original_image: Image.Image, image_id: str) -> None:
    """保留 EasyOCR 备用入口，不参与默认 AI 科研数据整理流程。"""
    review_key = f"ocr_review_{image_id}"
    enable_preprocessing = st.checkbox("启用图片预处理", value=True, key=f"preprocess_{image_id}")
    st.caption("预处理包括自动旋正、灰度化、提升对比度和适度锐化。")

    if st.button("开始备用 OCR 识别", key=f"run_easyocr_{image_id}"):
        try:
            with st.spinner("正在进行本地 OCR 识别，请稍候……"):
                reader = load_ocr_reader()
                raw_result = recognize_image(reader, original_image)
                processed_result = None
                if enable_preprocessing:
                    processed_result = recognize_image(reader, preprocess_image(original_image))
            st.session_state["ocr_raw_result"] = raw_result
            st.session_state["ocr_processed_result"] = processed_result
            st.session_state["ocr_result_image_id"] = image_id
            st.session_state[review_key] = processed_result or raw_result
        except Exception as error:
            st.error("备用 OCR 识别失败，请查看错误信息。")
            st.exception(error)

    if st.session_state.get("ocr_result_image_id") == image_id:
        raw_column, processed_column = st.columns(2)
        with raw_column:
            st.text_area("原图 OCR 结果（机器识别，可能有误）", value=st.session_state["ocr_raw_result"], height=220, disabled=True)
        with processed_column:
            processed_result = st.session_state["ocr_processed_result"]
            if processed_result is None:
                st.info("未启用图片预处理。")
            else:
                st.text_area("预处理后 OCR 结果（机器识别，可能有误）", value=processed_result, height=220, disabled=True)
        st.text_area("人工校对结果", key=review_key, height=260)


def render_developer_mock(uploaded_image, image_id: str) -> None:
    """只在开发模式显示的 MockProvider 测试入口。"""
    mock_key = f"mock_result_{image_id}"
    if st.button("运行模拟视觉处理", key=f"run_mock_{image_id}"):
        source_file = SourceFile(uploaded_image.name, uploaded_image.type or "image", uploaded_image.getvalue())
        st.session_state[mock_key] = process_experiment_images([source_file], provider_name="mock")
    if mock_key in st.session_state:
        mock_result = st.session_state[mock_key]
        st.warning("以下内容为模拟 AI 结果，不能当作真实实验测量数据。")
        st.write("原始模拟文本：", mock_result.raw_text)
        st.dataframe(pd.DataFrame([row.values for row in mock_result.rows]), width="stretch")
        render_mock_validation_panel(mock_result, f"developer-{image_id}")


st.title("AI 科研数据整理")
st.write("上传一张实验记录图片，AI 会整理为可确认的数据，再生成 Excel。")
st.caption("主流程：上传图片 → AI 视觉整理 → 人工确认不确定项 → 下载 Excel")
st.info("AI 结果是建议，不会自动覆盖原始实验记录；请确认数字、单位、样品编号和处理编号。")

uploaded_image = st.file_uploader("上传实验记录图片", type=["png", "jpg", "jpeg"], accept_multiple_files=False)

if uploaded_image is None:
    st.info("请先上传一张 png、jpg 或 jpeg 实验记录图片。")
else:
    image_id = f"{uploaded_image.name}-{uploaded_image.size}"
    if st.session_state.get("ocr_image_id") != image_id:
        st.session_state["ocr_image_id"] = image_id
        st.session_state.pop("ocr_result_image_id", None)
        st.session_state.pop("ocr_raw_result", None)
        st.session_state.pop("ocr_processed_result", None)

    try:
        image_read_started = time.perf_counter()
        original_image = Image.open(uploaded_image).convert("RGB")
        timings_key = f"doubao_timings_{image_id}"
        timings = st.session_state.setdefault(timings_key, {})
        timings["image_read_seconds"] = time.perf_counter() - image_read_started
    except (UnidentifiedImageError, OSError, ValueError) as error:
        st.error("图片读取失败，请检查图片格式。")
        st.exception(error)
    else:
        st.image(original_image, caption="原始实验记录图片", width="stretch")
        st.write(f"文件名：{uploaded_image.name}　文件大小：{uploaded_image.size / 1024 / 1024:.2f} MB")

        layout_detection = detect_large_image_layout(original_image)
        if layout_detection["suggest_large_pipeline"]:
            st.info(
                "AI 布局建议：这张图片可能是横向多栏大图，建议在下方开启“大图四栏预处理”。"
                f"（判断置信度：{layout_detection['confidence']:.0%}）"
            )
        else:
            st.caption(
                "AI 布局建议：使用普通单图流程。你仍可以在高级设置中手动启用大图四栏预处理。"
            )

        with st.expander("高级设置（测试）", expanded=False):
            enable_preprocessing = st.checkbox(
                "启用大图四栏预处理（灰度测试）",
                value=False,
                help="仅适用于已验证的80样品横向四栏图片；会在内存中旋正、切分四栏并分别调用模型。",
                key=f"enable_preprocessing_{image_id}",
            )

        with st.expander("运行诊断信息", expanded=False):
            diagnostics = build_runtime_diagnostics(enable_preprocessing)
            st.code("\n".join(f"{label}：{value}" for label, value in diagnostics.items()))

        doubao_key = f"doubao_result_{image_id}"
        if st.button("开始 AI 科研数据整理", type="primary", key=f"run_doubao_{image_id}"):
            try:
                source_file = SourceFile(uploaded_image.name, uploaded_image.type or "image", uploaded_image.getvalue())
                with st.spinner("AI 正在分析实验记录，请稍候……"):
                    api_call_started = time.perf_counter()
                    st.session_state[doubao_key] = process_experiment_images(
                        [source_file],
                        provider_name="doubao",
                        enable_preprocessing=enable_preprocessing,
                    )
                    clear_validation_state(st.session_state, image_id)
                    api_call_seconds = time.perf_counter() - api_call_started
                timings["api_call_seconds"] = api_call_seconds
                timings["model_return_seconds"] = api_call_seconds
                st.session_state.pop(f"doubao_confirmed_values_{image_id}", None)
                st.session_state.pop(f"doubao_confirmation_records_{image_id}", None)
                st.session_state.pop(f"doubao_editor_{image_id}", None)
            except Exception as error:
                print(type(error))
                print(error.__dict__)
                st.error("AI模型处理失败，请查看错误信息。")
                with st.expander("查看详细错误信息"):
                    st.code(str(error))
                    raw_content = getattr(error, "raw_content", None)
                    if raw_content is not None:
                        st.code(
                            "原始 content 调试信息：\n"
                            f"repr(content)：{raw_content!r}\n"
                            f"content 长度：{len(raw_content)}\n"
                            f"content 前500字符：\n{raw_content[:500]}"
                        )
                    else:
                        st.caption("此次异常没有携带原始 content 调试信息。")

        if doubao_key in st.session_state:
            try:
                render_ai_result(st.session_state[doubao_key], image_id, timings)
            except Exception as error:
                st.error("AI结果已返回，但页面解析失败。")
                st.exception(error)

        try:
            with st.expander("高级/备用 OCR", expanded=False):
                st.caption("这是本地 EasyOCR 文字识别备用功能，不生成结构化科研数据，也不调用 AI 视觉模型。")
                render_backup_ocr(original_image, image_id)
        except Exception as error:
            st.error("备用 OCR 页面显示失败，请查看错误信息。")
            st.exception(error)

        if st.query_params.get("developer") == "true":
            try:
                with st.expander("开发测试：模拟视觉结果", expanded=False):
                    st.caption("仅用于开发验证，普通用户不会看到此区域。")
                    render_developer_mock(uploaded_image, image_id)
            except Exception as error:
                st.error("开发测试页面显示失败，请查看错误信息。")
                st.exception(error)
