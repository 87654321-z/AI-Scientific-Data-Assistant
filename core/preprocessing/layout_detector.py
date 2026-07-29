"""本地大图布局判断工具。

该模块只根据图片尺寸和方向给出建议，不调用视觉模型，也不自动切换识别流程。
"""

from __future__ import annotations

from typing import TypedDict

from PIL import Image, ImageOps


class LayoutDetection(TypedDict):
    """页面用于展示的布局判断结果。"""

    layout_type: str
    suggest_large_pipeline: bool
    confidence: float


# 这些尺寸来自已验证的 80 样品横向四栏记录图片。
_MIN_PORTRAIT_WIDTH = 1100
_MIN_PORTRAIT_HEIGHT = 1900
_MIN_LANDSCAPE_WIDTH = 1900
_MIN_LANDSCAPE_HEIGHT = 1100


def detect_large_image_layout(image: Image.Image) -> LayoutDetection:
    """根据尺寸和方向判断是否建议使用大图四栏预处理。

    结果只是建议：调用方必须继续让用户手动决定是否启用预处理。
    """
    corrected = ImageOps.exif_transpose(image)
    width, height = corrected.size

    is_portrait_candidate = (
        height > width
        and width >= _MIN_PORTRAIT_WIDTH
        and height >= _MIN_PORTRAIT_HEIGHT
    )
    is_landscape_candidate = (
        width > height
        and width >= _MIN_LANDSCAPE_WIDTH
        and height >= _MIN_LANDSCAPE_HEIGHT
    )

    if is_portrait_candidate:
        return {
            "layout_type": "portrait_four_column_candidate",
            "suggest_large_pipeline": True,
            "confidence": 0.90,
        }
    if is_landscape_candidate:
        return {
            "layout_type": "landscape_four_column_candidate",
            "suggest_large_pipeline": True,
            "confidence": 0.85,
        }
    return {
        "layout_type": "standard_image",
        "suggest_large_pipeline": False,
        "confidence": 0.80,
    }
