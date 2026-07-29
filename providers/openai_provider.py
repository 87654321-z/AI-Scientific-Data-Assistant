"""未来 OpenAI 适配层的占位类；当前不联网，未来只从环境变量读取密钥。"""

from providers.base_vision_provider import VisionProvider


class OpenAIProvider(VisionProvider):
    name = "openai"

    def process_images(self, images, experiment_context=None):
        raise NotImplementedError("OpenAI 提供商尚未接入，本项目当前不会发起网络请求。")
