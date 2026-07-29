"""所有视觉模型提供商都遵循的接口。"""

from abc import ABC, abstractmethod

from core.schemas import ExperimentResult, SourceFile


class VisionProvider(ABC):
    name: str

    @abstractmethod
    def process_images(
        self,
        images: list[SourceFile],
        experiment_context: str | None = None,
    ) -> ExperimentResult:
        """把图片元数据和可选的内存字节内容转换为统一实验结果。"""
