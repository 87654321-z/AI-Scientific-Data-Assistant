"""80 样品横向多栏布局边界框的临时诊断脚本。"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from openai import OpenAI

from providers.doubao_provider import DoubaoProvider


OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "debug_bbox_crops"
EXPECTED_RANGES = ["1-20", "21-40", "41-60", "61-80"]

BBOX_PROMPT = """你是一名科研实验记录布局分析助手。请分析这张图片中的编号布局。

图片中可能存在横向多栏排列。请不要识别实验数值，只需要找到每个编号范围对应的区域位置。

只返回严格有效的 JSON，不要 Markdown、解释文字或任何其他字段：
{
  "layout_type": "",
  "regions": [
    {"range": "1-20", "bbox": [x1, y1, x2, y2]},
    {"range": "21-40", "bbox": [x1, y1, x2, y2]},
    {"range": "41-60", "bbox": [x1, y1, x2, y2]},
    {"range": "61-80", "bbox": [x1, y1, x2, y2]}
  ]
}

bbox 必须使用当前原始图片的像素坐标，且精确覆盖对应编号范围及其紧邻测量数字。不要输出实验数值、raw_text 或任何解释文字。"""


def load_settings() -> tuple[str, str, str]:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("ARK_MODEL")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    if not api_key or not model:
        raise ValueError("未读取到 ARK_API_KEY 或 ARK_MODEL。")
    return api_key, model, base_url


def validate_bbox(bbox: object, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    if not all(isinstance(value, int) for value in bbox):
        return None
    x1, y1, x2, y2 = bbox
    width, height = image_size
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        return None
    return x1, y1, x2, y2


def main() -> None:
    parser = argparse.ArgumentParser(description="豆包编号栏位边界框临时诊断")
    parser.add_argument("image", help="待诊断图片路径")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise ValueError("找不到测试图片。")
    file_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    api_key, model, base_url = load_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)
    content = DoubaoProvider()._request_vision_text(
        client, model, BBOX_PROMPT, file_type, image_base64
    )

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print("JSON 解析成功：否")
        print("模型原始输出：")
        print(content)
        return

    regions = data.get("regions", [])
    print("JSON 解析成功：是")
    print(f"布局类型：{data.get('layout_type')}")
    print(f"返回 region 数量：{len(regions) if isinstance(regions, list) else '无效'}")
    if not isinstance(regions, list):
        return

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    valid_count = 0
    with Image.open(image_path) as source:
        for region in regions:
            if not isinstance(region, dict):
                continue
            range_name = region.get("range")
            bbox = validate_bbox(region.get("bbox"), source.size)
            print(f"范围：{range_name}，bbox：{region.get('bbox')}，有效：{bbox is not None}")
            if range_name not in EXPECTED_RANGES or bbox is None:
                continue
            crop = source.crop(bbox)
            output_path = OUTPUT_DIRECTORY / f"bbox_{range_name.replace('-', '_')}.png"
            crop.save(output_path, format="PNG")
            print(f"已保存裁剪图：{output_path}，尺寸：{crop.size}")
            valid_count += 1
    print(f"有效 bbox 数量：{valid_count}")
    if valid_count != 4:
        print("模型原始输出：")
        print(content)


if __name__ == "__main__":
    main()
