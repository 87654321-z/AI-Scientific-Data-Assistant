"""预处理灰度工作流的本地 Mock 验证，不调用 API。"""

from io import BytesIO

from PIL import Image

from core.experiment_parser import process_experiment_images
from core.schemas import SourceFile


def make_verified_size_image() -> bytes:
    image = Image.new("RGB", (1279, 2275), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_original_and_preprocessed_modes() -> None:
    source = SourceFile("verified_layout.png", "image/png", make_verified_size_image())

    original_result = process_experiment_images([source], provider_name="mock")
    preprocessed_result = process_experiment_images(
        [source], provider_name="mock", enable_preprocessing=True
    )

    assert len(original_result.rows) == 1
    assert len(preprocessed_result.rows) == 4
    assert preprocessed_result.source_files == [source]
    assert "预处理灰度测试已启用" in preprocessed_result.warnings[0]
