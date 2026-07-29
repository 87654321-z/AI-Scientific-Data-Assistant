"""最小化验证火山引擎 Ark 图片理解接口。

运行示例：
    .\\.venv\\Scripts\\python tests\\test_doubao_vision.py C:\\path\\to\\record.jpg

不传入图片路径时，程序会生成并删除一张临时的 API 测试图片。
"""

from __future__ import annotations

import argparse
import base64
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg"}


def load_ark_settings() -> tuple[str, str, str]:
    """读取本地 .env；不会输出 API Key 的实际值。"""
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("ARK_MODEL")
    base_url = os.getenv(
        "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
    )
    if not api_key:
        raise ValueError("未读取到 ARK_API_KEY，请检查项目根目录的 .env 文件。")
    if not model:
        raise ValueError("未读取到 ARK_MODEL，请检查项目根目录的 .env 文件。")
    return api_key, model, base_url


def create_temporary_demo_image() -> Path:
    """生成临时测试图片，内容是模拟数据，不代表真实实验测量。"""
    image = Image.new("RGB", (640, 240), "white")
    drawer = ImageDraw.Draw(image)
    drawer.text(
        (30, 30),
        "API TEST IMAGE (SIMULATED DATA)\nSample: A-01\nValue: 12.34 g",
        fill="black",
        spacing=10,
    )
    file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    file.close()
    image.save(file.name, format="PNG")
    return Path(file.name)


def image_to_data_url(image_path: Path) -> str:
    """把本地 PNG/JPG/JPEG 图片转换为 Ark 可接收的数据 URL。"""
    if not image_path.is_file():
        raise ValueError(f"找不到图片：{image_path}")
    suffix = image_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("只支持 png、jpg、jpeg 图片。")
    mime_type = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def request_vision_result(image_path: Path) -> str:
    """发送一张图片，返回模型的原始文本结果。"""
    api_key, model, base_url = load_ark_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请简短说明你在图片中看到的文字和数字。",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_to_data_url(image_path)},
                    },
                ],
            }
        ],
    )
    return response.choices[0].message.content or "（模型没有返回文本内容）"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ark 豆包视觉最小连接测试")
    parser.add_argument("image", nargs="?", help="本地 png、jpg 或 jpeg 图片路径")
    args = parser.parse_args()

    temporary_image: Path | None = None
    try:
        if args.image:
            image_path = Path(args.image).expanduser().resolve()
            image_kind = "用户提供的本地图片"
        else:
            temporary_image = create_temporary_demo_image()
            image_path = temporary_image
            image_kind = "临时生成的 API 测试图片（模拟数据）"

        api_key, model, base_url = load_ark_settings()
        print(".env 配置读取成功：ARK_API_KEY、ARK_MODEL、ARK_BASE_URL 均已提供。")
        print(f"测试图片：{image_kind}，文件名：{image_path.name}")
        print(f"调用模型：{model}")
        print(f"接口地址：{base_url}")

        result = request_vision_result(image_path)
        print("Doubao API 调用成功，已收到模型返回结果。")
        print("模型原始返回：")
        print(result)
    except Exception as error:
        print(f"测试失败：{error}")
        raise SystemExit(1) from error
    finally:
        if temporary_image and temporary_image.exists():
            temporary_image.unlink()


if __name__ == "__main__":
    main()
