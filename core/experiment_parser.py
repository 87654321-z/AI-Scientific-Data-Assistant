"""平台无关的图片到结构化实验数据主流程。"""

from core.schemas import ExperimentResult, SourceFile
from core.preprocessing.region_workflow import process_verified_preprocessed_image
from providers.provider_factory import create_vision_provider


def process_experiment_images(
    images: list[SourceFile],
    provider_name: str,
    experiment_context: str | None = None,
    enable_preprocessing: bool = False,
    enable_preproc: bool = False,
) -> ExperimentResult:
    """处理图片信息；预处理开关默认关闭，保持原有单图流程。

    ``enable_preproc`` 是 OCR 页面旧调用名称的兼容参数；任一开关为真时，
    才使用已验证的大图四栏预处理流程。
    """
    provider = create_vision_provider(provider_name)
    if enable_preprocessing or enable_preproc:
        return process_verified_preprocessed_image(images, provider, experiment_context)
    return provider.process_images(images, experiment_context)
