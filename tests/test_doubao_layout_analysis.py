"""80 样品横向多栏布局理解的临时诊断脚本。"""

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

LAYOUT_PROMPT = """你是一名科研实验记录布局分析助手。请分析这张图片。

重点任务：
第一步：判断图片中的编号排列方式。
如果发现横向多栏排列，例如 1-20、21-40、41-60、61-80，请不要按照图片视觉行输出，必须展开为连续编号 1、2、3……80。

第二步：只输出一个有效 JSON 对象：
{
  "layout_type": "",
  "detected_ranges": [],
  "expanded_sample_ids": [],
  "rows_count": 0,
  "description": ""
}

layout_type 用于描述图片布局，例如 "horizontal_multi_column"。
detected_ranges 例如 ["1-20", "21-40", "41-60", "61-80"]。
expanded_sample_ids 必须输出展开后的连续编号列表。
rows_count 是最终展开后的编号数量。
description 简短说明你对布局的理解。

禁止输出完整实验数据、测量值、raw_text、uncertain_items、Markdown 或任何其他字段。"""


def load_settings() -> tuple[str, str, str]:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("ARK_MODEL")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    if not api_key or not model:
        raise ValueError("未读取到 ARK_API_KEY 或 ARK_MODEL。")
    return api_key, model, base_url


def read_image(image_path: Path) -> tuple[str, str]:
    suffix = image_path.suffix.lower()
    if not image_path.is_file() or suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("请提供存在的 png、jpg 或 jpeg 图片。")
    file_type = "image/png" if suffix == ".png" else "image/jpeg"
    return file_type, base64.b64encode(image_path.read_bytes()).decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description="豆包横向多栏布局临时诊断")
    parser.add_argument("image", help="待诊断图片路径")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    file_type, image_base64 = read_image(image_path)
    api_key, model, base_url = load_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    content = DoubaoProvider()._request_vision_text(
        client, model, LAYOUT_PROMPT, file_type, image_base64
    )
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print("JSON 解析成功：否")
        print("模型原始输出：")
        print(content)
        return

    sample_ids = data.get("expanded_sample_ids", [])
    is_complete = (
        isinstance(sample_ids, list)
        and sample_ids == list(range(1, 81))
        and data.get("rows_count") == 80
    )
    print(f"布局类型：{data.get('layout_type')}")
    print(f"编号范围：{data.get('detected_ranges')}")
    print(f"expanded_sample_ids 数量：{len(sample_ids) if isinstance(sample_ids, list) else '无效'}")
    print(f"rows_count：{data.get('rows_count')}")
    print(f"识别到横向四栏布局：{data.get('layout_type') == 'horizontal_multi_column'}")
    print(f"成功得到80个连续编号：{is_complete}")
    if not is_complete:
        print("模型原始输出：")
        print(content)


if __name__ == "__main__":
    main()
