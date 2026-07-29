"""按名称选择提供商，避免核心逻辑依赖某个平台。"""

from providers.doubao_provider import DoubaoProvider
from providers.mock_vision_provider import MockVisionProvider


def create_vision_provider(provider_name: str):
    if provider_name == "mock":
        return MockVisionProvider()
    if provider_name == "doubao":
        return DoubaoProvider()
    raise ValueError(f"当前不可用的视觉提供商：{provider_name}")
