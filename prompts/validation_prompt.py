"""为独立 Validation 阶段构造精简、只读 Prompt。"""

import json
from typing import Any

from core.schemas import ExperimentResult


def build_validation_snapshot(
    experiment_result: ExperimentResult,
    experiment_context: str | None = None,
) -> dict[str, Any]:
    """提取校验必需数据，不包含图片、日志、最终值或 API 配置。"""
    columns = [
        {
            "internal_name": column.internal_name,
            "display_name": column.display_name,
            "original_unit": column.original_unit or column.unit,
        }
        for column in experiment_result.columns
    ]
    rows = []
    for row_index, row in enumerate(experiment_result.rows, start=1):
        observed_values = row.observed_values or row.values
        rows.append({
            "row_index": row_index,
            "values": dict(observed_values),
            "replicate_group": row.replicate_group,
            "replicate_index": row.replicate_index,
        })
    return {
        "columns": columns,
        "observed_rows": rows,
        "experiment_context": experiment_context,
    }


def build_validation_prompt(
    experiment_result: ExperimentResult,
    experiment_context: str | None = None,
) -> str:
    """要求模型只检查已有结构化观察数据。"""
    snapshot = build_validation_snapshot(experiment_result, experiment_context)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return f"""你是一名科研实验数据质量检查助手。

输入是 Extraction 阶段已经生成的结构化实验观察数据，不是原始图片。
任务：只检查这些已有结构化数据，发现问题并提供建议；不要重新识别图片。

最高优先级规则：
1. 输入中的 observed_rows 是只读观察记录，不得修改、删除、合并、补写或重新排序。
2. 不得返回修改后的 observed_rows，也不得把 suggested_value 当作真实实验数据。
3. 缺失的实验测量值不得根据规律推算或编造。
4. 无法绑定到明确行和字段的问题，只能写入 warnings，不能猜测位置。
5. 建议必须等待用户确认；confidence 不能授权自动修改。

最小检查范围：
- 关键字段为空；
- 同列数据类型明显不一致；
- 处理编号或样品编号结构明显异常；
- replicate_group 相同但 replicate_index 缺失、重复或明显不连续；
- 字段单位缺失或冲突；
- 数值中出现明显非数值字符；
- 包含 ? 或 [模糊字符] 等需要人工检查的内容；
- 与同列上下文明显不一致的可疑值。

输出规则：
- 有合理候选值时放入 suggestions。
- 没有合理候选但需要检查时放入 uncertain_items，suggested_value 为 null。
- 不同单元格必须分别输出，不能合并。
- 所有涉及某个具体实验数据的问题，都必须同时返回 row_index、column_name、observed_value、suggested_value、reason、confidence 和 location_status。
- row_index 必须直接使用输入 observed_rows 中从 1 开始的 row_index；禁止改成数组下标或自行猜测行号。
- column_name 必须逐字使用输入 columns 中的 internal_name；禁止使用中文显示名、简称或新造字段名。
- observed_value 必须逐字复制对应行对应字段的输入值，不能改写或使用其他行的值。
- 行号和字段名都能明确绑定时，location_status 必须为 resolved。
- 无法可靠确定具体行号或字段名时，不得伪造位置；应将该问题写入 warnings。若仍输出 finding，则 row_index 和 column_name 必须为 null，location_status 必须为 unknown，且该项不会进入人工确认。
- 不要为同一个无法定位的全局问题逐行生成 finding；使用一条简短 warning 即可。
- reason 只写一句简短中文，不输出长篇推理。
- issue_type 仅使用 missing_value、type_mismatch、identifier_pattern、unit_inconsistency、replicate_inconsistency、numeric_format、possible_outlier、unresolved_character、other。
- scope 仅使用 cell、row、column、global。
- confidence 仅使用 low、medium、high。

只返回严格 JSON，不要 Markdown，不要解释文字：
{{
  "warnings": ["无法可靠绑定到单元格的简短提醒"],
  "suggestions": [
    {{
      "finding_id": "validation-0001",
      "scope": "cell",
      "row_index": 1,
      "column_name": "字段内部名",
      "observed_value": "输入中的原始观察值",
      "issue_type": "identifier_pattern",
      "reason": "一句简短中文原因",
      "suggested_value": "候选值",
      "confidence": "low",
      "location_status": "resolved"
    }}
  ],
  "uncertain_items": []
}}

禁止输出 columns、observed_rows、raw_text、图片内容、完整输入副本或分析过程。
最终输出只允许包含 warnings、suggestions 和 uncertain_items 三个顶层字段。

待检查数据：
{snapshot_json}"""
