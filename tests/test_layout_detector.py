"""大图布局自动建议的本地 Mock 测试，不调用模型或 API。"""

from PIL import Image

from core.preprocessing.layout_detector import detect_large_image_layout


def test_verified_portrait_layout_is_suggested() -> None:
    result = detect_large_image_layout(Image.new("RGB", (1279, 2275), "white"))

    assert result["layout_type"] == "portrait_four_column_candidate"
    assert result["suggest_large_pipeline"] is True
    assert result["confidence"] == 0.90


def test_standard_image_keeps_normal_pipeline_suggestion() -> None:
    result = detect_large_image_layout(Image.new("RGB", (800, 600), "white"))

    assert result["layout_type"] == "standard_image"
    assert result["suggest_large_pipeline"] is False
    assert result["confidence"] == 0.80
