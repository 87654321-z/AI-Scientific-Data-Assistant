"""不联网、不收费的模拟视觉提供商。"""

from core.schemas import ColumnInfo, DataRow, ExperimentResult, SourceFile, UncertainItem
from providers.base_vision_provider import VisionProvider


class MockVisionProvider(VisionProvider):
    """返回固定模拟数据，用于验证完整工作流。"""

    name = "mock_vision"

    def process_images(
        self,
        images: list[SourceFile],
        experiment_context: str | None = None,
    ) -> ExperimentResult:
        return ExperimentResult(
            source_files=images,
            raw_text="【模拟 AI 结果】样品 A-01，对照组，重复 1，测量值 12.3。",
            columns=[
                ColumnInfo("sample_id", "样品编号", None, False, "ai_suggestion"),
                ColumnInfo("treatment_group", "处理组", None, False, "ai_suggestion"),
                ColumnInfo("replicate", "重复编号", None, False, "ai_suggestion"),
                ColumnInfo("measurement_value", "测量值", None, False, "ai_suggestion"),
            ],
            rows=[self._suggested_row()],
            ai_suggested_rows=[self._suggested_row()],
            uncertain_items=[
                UncertainItem("样品编号", "A-0?", "最后一位字符无法确定。"),
                UncertainItem("测量值", "12.3", "小数点需要人工确认。"),
                UncertainItem("测量值单位", "缺失", "原始记录没有明确单位。"),
            ],
            warnings=["这是模拟 AI 结果，不是实际图片识别结果。", "请人工确认样品编号、小数点和测量单位。"],
            provider=self.name,
        )

    @staticmethod
    def _suggested_row() -> DataRow:
        return DataRow(
            values={
                "sample_id": "A-0?",
                "treatment_group": "对照组",
                "replicate": 1,
                "measurement_value": 12.3,
            },
            field_sources={
                "sample_id": "ai_suggestion",
                "treatment_group": "ai_suggestion",
                "replicate": "ai_suggestion",
                "measurement_value": "ai_suggestion",
            },
        )
