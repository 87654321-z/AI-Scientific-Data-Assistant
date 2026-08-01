"""按名称创建 Validation Provider。"""

from providers.doubao_validation_provider import DoubaoValidationProvider
from providers.mock_validation_provider import MockValidationProvider


def create_validation_provider(provider_name: str):
    if provider_name == "mock":
        return MockValidationProvider()
    if provider_name == "doubao":
        return DoubaoValidationProvider()
    raise ValueError(f"当前不可用的 Validation Provider：{provider_name}")
