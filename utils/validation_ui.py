"""Mock Validation 的 Streamlit 状态和展示。"""

from collections.abc import Callable, MutableMapping

import pandas as pd
import streamlit as st

from core.schemas import ExperimentResult
from core.validation_quality import (
    ValidationDisplayResult,
    build_validation_display_result,
)
from core.validation_service import validate_experiment_result
from core.validation_schemas import ValidationFinding, ValidationResult


VALIDATION_NOT_RUN = "not_run"
VALIDATION_RUNNING = "running"
VALIDATION_SUCCEEDED = "succeeded"
VALIDATION_FAILED = "failed"


def validation_state_keys(result_id: str) -> dict[str, str]:
    """生成与某次 Extraction 结果绑定的 Session State 键。"""
    return {
        "status": f"validation_status_{result_id}",
        "result": f"validation_result_{result_id}",
        "error": f"validation_error_{result_id}",
    }


def clear_validation_state(
    state: MutableMapping,
    result_id: str,
) -> None:
    """Extraction 重新运行后清除旧 Validation，避免结果错配。"""
    for key in validation_state_keys(result_id).values():
        state.pop(key, None)


def get_validation_status(state: MutableMapping, result_id: str) -> str:
    """读取 Validation 状态；首次进入时为未运行。"""
    keys = validation_state_keys(result_id)
    return state.get(keys["status"], VALIDATION_NOT_RUN)


def run_validation(
    state: MutableMapping,
    experiment_result: ExperimentResult,
    result_id: str,
    provider_name: str,
    validator: Callable = validate_experiment_result,
) -> bool:
    """运行指定 Validation Provider，并与 Extraction 分开保存状态。"""
    keys = validation_state_keys(result_id)
    state[keys["status"]] = VALIDATION_RUNNING
    state.pop(keys["result"], None)
    state.pop(keys["error"], None)
    try:
        validation_result = validator(
            experiment_result,
            provider_name=provider_name,
        )
    except Exception as error:
        state[keys["status"]] = VALIDATION_FAILED
        state[keys["error"]] = str(error)
        return False

    state[keys["result"]] = validation_result
    state[keys["status"]] = VALIDATION_SUCCEEDED
    return True


def run_mock_validation(
    state: MutableMapping,
    experiment_result: ExperimentResult,
    result_id: str,
    validator: Callable = validate_experiment_result,
) -> bool:
    """保留 Step 2.1 的 Mock 调用名称，供开发和回归测试使用。"""
    return run_validation(
        state,
        experiment_result,
        result_id,
        provider_name="mock",
        validator=validator,
    )


def render_validation_panel(
    experiment_result: ExperimentResult,
    result_id: str,
    provider_name: str,
) -> None:
    """在 Extraction 结果下显示独立 Validation 区域。"""
    keys = validation_state_keys(result_id)
    status = get_validation_status(st.session_state, result_id)

    st.subheader("AI 数据检查")
    if provider_name == "mock":
        st.caption(
            "当前为 Mock 模拟检查，不调用真实 AI、不会产生费用，也不会修改 Extraction 原始数据。"
        )
    else:
        st.caption(
            "将使用当前配置的 AI 模型检查 Extraction 结构化数据，可能产生额外费用；"
            "检查结果不会自动修改原始数据。"
        )

    if status == VALIDATION_NOT_RUN:
        st.info("AI 数据检查尚未运行。")
    elif status == VALIDATION_RUNNING:
        st.info("AI 数据检查正在运行……")
    elif status == VALIDATION_SUCCEEDED:
        st.success("AI 数据检查运行成功。以下结果仅供人工检查。")
    elif status == VALIDATION_FAILED:
        st.error("结构化数据仍然可用，但 AI 数据检查运行失败。")
        with st.expander("查看 AI 数据检查详细错误", expanded=False):
            st.code(st.session_state.get(keys["error"], "未提供错误信息。"))

    button_label = "重新运行 AI 数据检查" if status in {
        VALIDATION_SUCCEEDED,
        VALIDATION_FAILED,
    } else "运行 AI 数据检查"
    if st.button(button_label, key=f"run_validation_{result_id}"):
        spinner_text = (
            "正在运行模拟数据检查……"
            if provider_name == "mock"
            else "AI 正在检查结构化数据，请稍候……"
        )
        with st.spinner(spinner_text):
            run_validation(
                st.session_state,
                experiment_result,
                result_id,
                provider_name=provider_name,
            )
        st.rerun()

    validation_result = st.session_state.get(keys["result"])
    if status != VALIDATION_SUCCEEDED or not isinstance(
        validation_result,
        ValidationResult,
    ):
        return

    _render_validation_result(validation_result)


def render_mock_validation_panel(
    experiment_result: ExperimentResult,
    result_id: str,
) -> None:
    """保留 Step 2.1 的开发模式入口。"""
    render_validation_panel(experiment_result, result_id, provider_name="mock")


def _render_validation_result(validation_result: ValidationResult) -> None:
    """使用 Quality Filter 分级显示，同时保留 Session State 中的原始结果。"""
    display_result = build_validation_ui_data(validation_result)
    summary = display_result.summary
    low_count = len(_findings_by_severity(display_result, "low"))
    folded_count = low_count + summary["limited_count"]

    summary_columns = st.columns(4)
    summary_columns[0].metric("原始发现", summary["raw_finding_count"])
    summary_columns[1].metric("当前展示", summary["displayed_finding_count"])
    summary_columns[2].metric("重复项", summary["duplicate_count"])
    summary_columns[3].metric("折叠/限制", folded_count)

    if display_result.suppressed_findings:
        st.caption(
            f"共有 {len(display_result.suppressed_findings)} 条发现因重复或数量限制"
            "未进入主展示列表，原始 Validation 结果仍完整保留。"
        )

    st.markdown("#### 警告")
    if display_result.warnings:
        for warning in display_result.warnings:
            st.warning(warning)
    else:
        st.info("没有全局警告。")

    high_rows = _findings_by_severity(display_result, "high")
    medium_rows = _findings_by_severity(display_result, "medium")
    low_rows = _findings_by_severity(display_result, "low")

    st.markdown("#### 高风险发现")
    if high_rows:
        st.dataframe(
            pd.DataFrame(high_rows),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("没有高风险发现。")

    st.markdown("#### 中风险发现")
    if medium_rows:
        st.dataframe(
            pd.DataFrame(medium_rows),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("没有中风险发现。")

    with st.expander(f"低风险发现（{len(low_rows)}）", expanded=False):
        if low_rows:
            st.dataframe(
                pd.DataFrame(low_rows),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("没有低风险发现。")


def build_validation_ui_data(
    validation_result: ValidationResult,
) -> ValidationDisplayResult:
    """为 UI 构造副本结果，原始 ValidationResult 继续保存在 Session State。"""
    return build_validation_display_result(validation_result)


def _findings_by_severity(
    display_result: ValidationDisplayResult,
    severity: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for category, findings in (
        ("AI 建议", display_result.suggestions),
        ("不确定项", display_result.uncertain_items),
    ):
        selected = [item for item in findings if item.severity == severity]
        rows.extend(_finding_rows(selected, category))
    return rows


def _finding_rows(
    findings: list[ValidationFinding],
    category: str = "不确定项",
) -> list[dict[str, object]]:
    """把结构化 finding 转为只读中文表格，不解析自然语言位置。"""
    confidence_names = {"high": "高", "medium": "中", "low": "低"}
    location_names = {
        "resolved": "已定位",
        "recovered": "已恢复定位",
        "global": "全局",
        "ambiguous": "位置不明确",
        "unresolved": "无法定位",
        "unvalidated": "尚未验证",
    }
    issue_names = {
        "missing_value": "缺失值",
        "type_mismatch": "数据类型不一致",
        "identifier_pattern": "实验编号格式可疑",
        "unit_inconsistency": "单位不一致",
        "replicate_inconsistency": "重复实验信息不一致",
        "numeric_format": "数字格式可疑",
        "possible_outlier": "数值可能异常",
        "unresolved_character": "字符无法确认",
        "other": "其他需检查问题",
    }
    return [
        {
            "类别": category,
            "行号": finding.row_index if finding.row_index is not None else "全局",
            "字段": finding.column_name or "未指定",
            "原始观察值": finding.observed_value,
            "问题类型": issue_names.get(finding.issue_type, "其他需检查问题"),
            "AI 建议值": finding.suggested_value,
            "原因": finding.reason,
            "置信度": confidence_names.get(finding.confidence, "低"),
            "定位状态": location_names.get(
                finding.location_status,
                "尚未验证",
            ),
        }
        for finding in findings
    ]
