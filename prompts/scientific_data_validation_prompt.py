"""用于首轮视觉识别后的只读校验提示词。"""


def build_scientific_data_validation_prompt(first_pass_json: str) -> str:
    """要求模型检查首轮结果；它不能返回或改写正式数据行。"""
    return f"""你是一名科研实验记录的数据质量检查员。

下面是同一张实验记录图片的第一次结构化识别 JSON：
{first_pass_json}

请再次查看图片，并且只做校验，不要重写、删除、合并或补全任何正式数据行。

重点检查：
1. 首轮结果中的每一条图片可见实验记录是否都保留了一个 observed_rows 行；若疑似漏行，指出其应在的行位置和可见片段。
2. 样品编号、处理编号、重复编号的格式是否异常。
3. 数字、小数点、正负号、加号、减号、斜杠、上标和下标是否可能错误。实验测量值优先识别为数字，禁止将数字识别为希腊字母、英文字母或特殊符号；例如不得将 `7.79` 识别为 `γ.79`。数字不确定时保留可见数字片段，例如 `7.?`，或保留原数字并创建 additional_uncertain_items，不得创造其他字符。
4. 单位是否缺失、模糊或异常。单位是字段级信息，不得作为数据行新增或删除的理由。
5. 可以给出 suggested_value 或 suggested_unit，但它们只能是建议，不能替换 observed_value 或 original_unit。
6. 进行实验规律一致性检查：根据同列变量规律、相邻行模式、图片中可见的实验设计、变量取值集合和排列顺序，检查处理编号是否出现异常新变量或异常组合。字符存在多种解释、组合不符合规律、或与其他行明显不同，都必须生成 additional_uncertain_items。只要存在合理候选，就必须给出 suggested_value，即使只是低置信度建议；例如 S0/[模糊字符]/E+/N2 在同列规律支持 L 时，应建议 S0/L/E+/N2。只有完全没有合理候选时才允许 suggested_value 为 null。示例：同一变量在其余记录中只出现 L/H，而某行出现 XL、HL、Il 等异常组合时，必须保留 observed_value，并给出 basis 和 confidence；建议绝不能替换 observed_value。
7. 对重复实验逐行检查：replicate_group 和 replicate_index 只是辅助信息，不能替代 treatment_id。若图片的每条重复行都可见处理编号，则每条 observed_rows 行都应保留完整 treatment_id；不得只在第一条重复行填写 treatment_id，也不得将后续重复行设为 null。
8. 即使连续多行存在相同的模糊字符、相同异常组合或相同建议，也必须按实际行分别生成 additional_uncertain_items，并在 location 中分别写明行号；禁止将多个行位置合并为一次报告。

只返回 JSON，不要 Markdown，格式如下：
{{
  "additional_uncertain_items": [
    {{
      "location": "第N行字段名，或字段名单位",
      "target_type": "cell、field_name 或 field_unit",
      "column_name": "目标字段内部名；field_name 和 field_unit 必填",
      "observed_value": "首轮或图片可见内容；没有则为null",
      "suggested_value": "可选的AI建议；没有合理建议则为null",
      "basis": "发现问题的依据",
      "confidence": "low、medium 或 high",
      "content": "target_type=...; column_name=...; observed_value=...; suggested_value=...; confidence=...",
      "reason": "简要校验原因"
    }}
  ],
  "warnings": ["需要用户注意的问题"]
}}

若没有发现问题，additional_uncertain_items 必须返回 []。不得使用省略号代替无法确认内容。"""
