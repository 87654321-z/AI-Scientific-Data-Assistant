"""统一的实验记录内部数据格式。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceFile:
    filename: str
    file_type: str
    content: bytes | None = None


@dataclass
class ColumnInfo:
    internal_name: str
    display_name: str
    unit: str | None
    confirmed: bool
    source: str
    # 单位是字段级信息，不能混入某一条实验记录中。
    # 首轮识别只能填写 original_unit；AI 推测和用户确认值分别单独保存。
    original_unit: str | None = None
    suggested_unit: str | None = None
    final_unit: str | None = None


@dataclass
class DataRow:
    values: dict[str, Any]
    field_sources: dict[str, str]
    # 图片中直接观察到的字段值；最终确认值写入 values 时仍可追溯原始观察。
    observed_values: dict[str, Any] = field(default_factory=dict)
    # 重复测量关系是行级元数据，不参与平均值或标准差计算。
    replicate_group: str | None = None
    replicate_index: int | None = None
    # 用户确认阶段的轻量状态：False 表示该行不纳入最终结果，但原始行仍保留。
    include_in_final: bool = True


@dataclass
class UncertainItem:
    location: str
    content: str
    reason: str


@dataclass
class ExperimentResult:
    source_files: list[SourceFile]
    raw_text: str
    columns: list[ColumnInfo]
    rows: list[DataRow]
    ai_suggested_rows: list[DataRow]
    uncertain_items: list[UncertainItem]
    warnings: list[str]
    provider: str
    user_confirmed: bool = False
    modification_records: list[str] = field(default_factory=list)
    # 仅保存本次运行的模型原始返回，供开发模式比较首轮与二次校验差异。
    model_response_logs: list[dict[str, str]] = field(default_factory=list)
