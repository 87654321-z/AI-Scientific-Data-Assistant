"""80 样品大图的极简豆包视觉输出测试。

此脚本仅用于评估单次模型输出是否会截断；不调用正式 Prompt、
不进入 ExperimentResult 解析，也不写入项目数据。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from openai import OpenAI

from providers.doubao_provider import DoubaoProvider


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg"}

TEST_PROMPT = """这是一次大图输出容量测试。只识别图片中的编号和其对应的一个数字。

只返回一个有效 JSON 对象，不要 Markdown，不要解释文字，必须严格使用以下结构：
{
  "rows": [
    {"id": "图片中的编号", "value": "对应数字"}
  ]
}

禁止输出 raw_text、uncertain_items、suggested_value、warnings、replicate_group、replicate_index，
也禁止输出任何其他字段。不要猜测或补全看不清的内容；无法确认时 value 写 null。"""


def load_settings() -> tuple[str, str, str]:
    """读取本地配置，不打印 API Key。"""
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("ARK_MODEL")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    if not api_key or not model:
        raise ValueError("未读取到 ARK_API_KEY 或 ARK_MODEL。")
    return api_key, model, base_url


def read_image(image_path: Path) -> tuple[str, str]:
    """按正式 Provider 相同的数据 URL 输入方式准备图片。"""
    suffix = image_path.suffix.lower()
    if not image_path.is_file() or suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("请提供存在的 png、jpg 或 jpeg 图片。")
    file_type = "image/png" if suffix == ".png" else "image/jpeg"
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return file_type, image_base64


def main() -> None:
    parser = argparse.ArgumentParser(description="豆包大图极简 JSON 输出测试")
    parser.add_argument("image", help="待测试的大图路径")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    file_type, image_base64 = read_image(image_path)
    api_key, model, base_url = load_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    # 复用正式 DoubaoProvider 的图片发送方式，但不进入正式解析流程。
    content = DoubaoProvider()._request_vision_text(
        client, model, TEST_PROMPT, file_type, image_base64
    )
    print(f"返回字符长度：{len(content)}")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print("JSON 解析成功：否")
        print("rows 数量：无法统计")
        return

    rows = data.get("rows")
    print("JSON 解析成功：是")
    print(f"rows 数量：{len(rows) if isinstance(rows, list) else '无效 rows 字段'}")


if __name__ == "__main__":
    main()
