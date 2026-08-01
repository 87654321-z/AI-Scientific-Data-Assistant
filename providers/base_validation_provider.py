"""所有 Validation 提供商遵循的独立接口。"""

from abc import ABC, abstractmethod

from core.schemas import ExperimentResult
from core.validation_schemas import ValidationResult


class ValidationProvider(ABC):
    """检查结构化实验数据，不负责图片提取。"""

    name: str

    @abstractmethod
    def validate_result(
        self,
        experiment_result: ExperimentResult,
        experiment_context: str | None = None,
    ) -> ValidationResult:
        """返回独立校验结果，不修改传入的 ExperimentResult。"""
