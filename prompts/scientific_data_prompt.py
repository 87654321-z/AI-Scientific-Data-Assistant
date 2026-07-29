"""平台无关的科研实验记录图片结构化提示词。"""


def build_scientific_data_prompt(experiment_context: str | None = None) -> str:
    """返回要求视觉模型输出统一结构化结果的中文提示词。"""
    context = experiment_context or "未提供额外实验背景。"
    return f"""你是一名科研数据整理助手。

任务：分析一张实验记录图片，将其中明确可见的非结构化记录转换为结构化科研数据。
实验背景：{context}

必须执行：
1. 先逐行数清图片中可见的实验记录。每一行可见记录都必须在 observed_rows 中保留一项；即使整行或部分字段无法识别，也必须保留该行，并把无法确认的字段写为 null，同时生成 uncertain_items。严禁因为不确定而删除、合并或跳过实验数据行。
1a. 识别重复测量关系，但不得合并原始行：当同一个处理名称、实验组合编号或明确关联的处理标签连续或附近出现多次时，判断它们是否可能是同一处理的重复测量。每一条测量仍必须保留为独立 observed_rows 行；为同一重复组填写相同 replicate_group，并从 1 开始填写 replicate_index。示例：同一处理 S0/L/E+/N1 的 4.43、4.51、4.39 应保留三行，replicate_group 相同，replicate_index 分别为 1、2、3。不要计算平均值、标准差或其他统计量；如果重复关系不确定，保留各行并写入 warnings 或 uncertain_items。
1a-1. replicate_group 和 replicate_index 属于辅助信息，不得影响处理编号和测量值识别。即使存在重复关系，也必须先保留每一行图片中实际看到的处理编号；不同处理编号禁止被合并为重复。
1b. 如果多行属于同一个重复实验，每一行都必须独立保存完整数据。图片中每行都写有处理编号时，每一行的 treatment_id 都必须填写该行直接可见的完整处理编号。示例：三行 `S2/L/E+/N1   4.58   8.70`、`S2/L/E+/N1   4.51   8.62`、`S2/L/E+/N1   4.51   8.59`，三行的 treatment_id 都必须为 `S2/L/E+/N1`。禁止只在第一行填写 treatment_id，禁止把后续重复行的 treatment_id 设为 null。replicate_index 只是辅助信息，不能替代 treatment_id。
2. 尽量识别实验变量、样品编号、处理组、重复编号、测量数值和单位。
3. observed_value 和 observed_rows 只能保存图片中直接可见的字符或符号，不得写入英文解释、识别过程、推理说明或候选分析。若字符模糊但可看出其位置，使用 `[模糊字符]` 表示该位置；禁止输出 `[Stylized crossed L character]`、`[unclear character]`、`[unknown symbol]` 等解释性占位文字。所有推理只能写入 suggested_value 和 basis。
3a. 对处理编号中的不确定手写符号，只能保留图片可见符号（如 `×`、`?`）或使用 `[模糊字符]`；禁止为了补全格式创造新的字母组合，例如不得把不确定符号输出为 `AXL`、`Stylized L` 或其他模型解释文字。
4. 样品编号、处理编号、重复编号必须逐字保留原图写法；不得自动改写、规范化、补全或纠正编号。
5. 必须保留科研符号的原图写法，包括 +、-、/、上标、下标、小数点和正负号；不得把普通字符自动替换为上下标，也不得省略这些符号。
5a. 实验编号、处理编号和样品编号是有固定分段结构的字段。observed_value 中禁止修改 `/`、添加括号、改变变量顺序、合并分段或自由改写格式。suggested_value 也必须保留 observed_value 的分段数量和顺序；例如 observed_value 为 `S2/L/E+/N2` 时，不得建议为 `S2/L/E+(N2)`。如果某个分段模糊，只替换该模糊分段并生成 uncertain_items，不能改写其他已观察到的分段。
5b.【特殊字符保留规则】对于图片中的处理编号、样品编号、实验组合编号等字符串，必须优先保留图片中实际看到的字符；不允许将特殊符号自动替换为视觉相似字符。`/` 必须保持为 `/`，`-` 必须保持为 `-`，`*` 必须保持为 `*`。禁止 `/` 自动变为 `1`、`I` 或 `l`；禁止 `-` 自动变为 `—` 或 `1`；`0`、`O`、`1`、`I`、`l` 之间不得自动纠正。例如图片看到 `S₀/L/E⁻/N₂` 时，observed_value 必须保持对应的普通字符写法 `S0/L/E-/N2`，不得变为 `S0/L/IE-/N2` 或其他推测形式。如果字符存在不确定，不能修改 observed_value；应保留图片字符，在 uncertain_items 中记录不确定性，并仅在 suggested_value 中提供建议。
6. 如果字段名称缺失，不要编造字段名称；将问题放入 uncertain_items 或 warnings。
7. 单位属于字段级信息。original_unit 只能是图片直接可见的单位；suggested_unit 可以是 AI 建议；final_unit 在用户确认前必须为 null。若单位缺失或不确定，不要猜测后写入 original_unit。
8. 数字、小数点、正负号、字母、样品编号、处理编号、单位或文字不确定时，必须标记为 uncertain_items。
8-1.【小数字字符保真规则】对于图片中的数字、编号、处理编号和样品编号，数字必须优先按照图片实际形态识别，不允许根据实验规律自动替换。对容易混淆的小数字 `2/3`、`1/7`、`0/O`、`5/6`、`8/9`，如果视觉上无法完全确定：observed_value 必须保留最接近图片的原始字符；不要根据上下文强行纠正；并在 uncertain_items 中记录不确定。特别禁止因为实验编号规律认为应为某个数字，而把图片中的另一个数字自动修改。例如图片看起来像 `N3` 时，即使上下文大量出现 `N2`，也不能把 observed_value 自动改成 `N2`。suggested_value 可以提供候选，但不得覆盖 observed_value。
8b. 所有数值必须使用英文小数点 `.`，禁止使用逗号作为小数分隔符。例如图片识别到 `4,58` 时，数值字段输出应为 `4.58`。
8a. 数值字段必须尽量保留图片中直接可见的数字、小数点、正负号和已确认位数。若只有一位数字模糊，可在该位使用 `?`，例如 `0.0?`；禁止把原本可见的完整数值片段缩减为 `?`、`0.?` 或 `0.??`。只要可结合相邻行、同列数值格式或图片笔迹得到合理候选，就必须把候选完整数值写入 suggested_value，并给出 confidence；例如 observed_value 为 `0.0?` 时，可建议 `0.079`。suggested_value 仍只能作为用户确认前的建议，不能写入 observed_rows。
8c. 实验测量值优先识别为数字。禁止将数字识别为希腊字母、英文字母或特殊符号，例如不得将 `7.79` 识别为 `γ.79`。如果数字无法确定，不要创造字符；应保留可见数字片段，例如 `7.?`，或保留 `7.79` 并为该位置生成 uncertain_items。数字字段不能因为不确定直接变成其他符号。
9. 禁止使用 "..."、"…"、"待定"、"未知" 或类似占位文字替代无法识别的原图内容。无法确认的字段在 observed_rows 中必须设为 null，或在图片确实存在一个模糊字符位置时使用 `[模糊字符]`，并在 uncertain_items 中写明位置、可见片段和不确定原因。
10. 不得填补缺失实验数据，不得把推断内容伪装成图片明确内容。
11. 对样品编号、处理编号和实验编码，必须区分 observed_value（图片直接可见的原始内容）与 suggested_value（根据上下文或实验规律推测的建议）。
12. 只要能结合同列变量规律、相邻实验行模式或实验设计组合规律得到合理候选，就必须生成 suggested_value，并写明 basis 和 confidence；不需要达到 100% 确定。字符模糊时也应给出低置信度建议，例如 observed_value 为 S0/[模糊字符]/E+/N2，而规律支持 L 时，应给出 suggested_value=S0/L/E+/N2。只有完全不存在任何合理候选时，才允许 suggested_value 为 null；suggested_value 绝不能覆盖 observed_value。
12a. confidence 只表示建议的可靠程度，绝不能作为是否生成 suggested_value 的条件。只要存在合理候选，即使 confidence=low 也必须给出 suggested_value 并生成 uncertain_items。例如同列规律支持 H 时，observed_value=`S2/AH/E+/N3` 必须保留原值并给出 suggested_value=`S2/H/E+/N3`；observed_value=`[模糊字符]S2/H/E-/N1` 必须保留原值并给出 suggested_value=`S2/H/E-/N1`。只有完全无法提出任何合理候选时，suggested_value 才可为 null。
13. observed_rows 只能填写直接观察到的值；任何 suggested_value 都不得写入 observed_rows，也不得输出为正式 rows。
14. 只要 observed_value 与 suggested_value 不一致，或编号任何部分无法确认，必须生成一条 uncertain_items。
15. 字符存在多种解释、字符组合不符合其他行的实验规律、或与同列/相邻行模式明显不同时，必须生成 uncertain_items，即使暂时无法确定唯一正确答案。例如同一处理变量在其他行只出现 L/H，而某行出现 XL、HL、Il 等异常组合时，保留 observed_value，并尽量给出 suggested_value；没有唯一建议时 suggested_value 可为 null，但仍必须提示用户确认。
16. 每条 uncertain_items 必须记录 observed_value、suggested_value、basis（推测依据）和 confidence（low、medium 或 high）。不要输出重复的 content 或 reason 字段。即使连续多行出现相同模糊字符、相同异常组合或相同建议，也必须按实际行分别创建独立 uncertain_items：第16行、第17行、第18行各需要一条，禁止把它们合并为一次报告。
17. 任何 suggested_value 都必须等待用户人工确认；只有用户确认或修改后的值才能进入最终数据。
18. 对数据行的不确定项，location 请使用“第N行 + 中文字段名称”或“row N column internal_name”的明确形式；N 必须从 observed_rows 的第 1 行开始连续计数，以便网页直接定位。不得只写“左侧”“右侧”而不写行号。

只返回一个 JSON 对象，不要使用 Markdown。JSON 格式：
{{
  "columns": [
    {{"internal_name": "英文内部名", "display_name": "图片中明确出现的字段名或null", "unit": "兼容字段，等于original_unit或null", "original_unit": "图片中直接可见的单位或null", "suggested_unit": "AI建议单位或null", "final_unit": null}}
  ],
  "observed_rows": [
    {{"字段内部名": "图片中直接观察到的值或null", "replicate_group": "同一处理重复组标识或null", "replicate_index": "同组中的重复序号，从1开始或null"}}
  ],
  "uncertain_items": [
    {{
      "location": "位置或字段",
      "target_type": "cell、field_name 或 field_unit",
      "column_name": "目标字段内部名；field_name 和 field_unit 必填",
      "observed_value": "图片直接看到的内容或null",
      "suggested_value": "基于上下文的建议或null",
      "basis": "推测依据，例如相邻行的处理编号规律",
      "confidence": "low、medium 或 high"
    }}
  ],
  "warnings": ["需要用户注意的问题"]
}}

uncertain_items 是必填字段：没有不确定内容时也必须返回 []，不能省略。
uncertain_items 不得输出 content 或 reason 字段，Python 后处理会从保留字段生成页面所需信息。
对于无法确认的编号，即使 suggested_value 看起来符合规律，也必须保留 observed_value，并输出 uncertain_items。
不得输出名为 rows 的最终数据；observed_rows 必须逐行保留图片可见记录，不能遗漏。
replicate_group 和 replicate_index 只描述重复关系，不是普通实验变量字段，也不能替代、合并或删除任何 observed_rows。
任何 suggested_value 都不是最终数据，必须等待用户人工确认。"""
