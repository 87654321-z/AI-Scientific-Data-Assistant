"""80 样品图片：先布局分析、再分栏识别的临时验证脚本。"""

from __future__ import annotations

import argparse
import base64
import io
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
from tests.test_doubao_layout_analysis import LAYOUT_PROMPT


# 原始照片中上方 Na+ 页面四个编号栏位。仅用于本次固定图片诊断。
REGIONS = {
    "区域1（1-20）": ((820, 170, 1070, 960), range(1, 21)),
    "区域2（21-40）": ((590, 170, 840, 960), range(21, 41)),
    "区域3（41-60）": ((360, 170, 610, 960), range(41, 61)),
    "区域4（61-80）": ((130, 170, 380, 960), range(61, 81)),
}

REGION_PROMPT = """这是一张科研记录图片中单独裁剪出的一个编号区域。
只识别每个样品编号和它紧邻的一个测量数字。

只返回一个有效 JSON 对象，不要 Markdown、解释文字或任何其他字段：
{
  "rows": [
    {"sample_id": "图片中的编号", "value": "对应数字"}
  ]
}

禁止输出 raw_text、columns、uncertain_items、suggested_value、warnings、
replicate_group、replicate_index。不要猜测或补全看不清的内容；无法确认时 value 写 null。"""


def load_settings() -> tuple[str, str, str]:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("ARK_MODEL")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    if not api_key or not model:
        raise ValueError("未读取到 ARK_API_KEY 或 ARK_MODEL。")
    return api_key, model, base_url


def request_text(client: OpenAI, model: str, prompt: str, file_type: str, image_base64: str) -> str:
    """复用正式 DoubaoProvider 的图片发送方法，不进入正式解析流程。"""
    return DoubaoProvider()._request_vision_text(client, model, prompt, file_type, image_base64)


def encode_png(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def parse_region(content: str, expected_ids: range) -> dict:
    """只统计临时测试结果，不改写模型返回。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"json_ok": False, "ids": [], "value_count": 0, "raw": content}

    rows = data.get("rows", [])
    if not isinstance(rows, list):
        return {"json_ok": True, "ids": [], "value_count": 0, "raw": content}
    ids = []
    value_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            sample_id = int(row.get("sample_id"))
        except (TypeError, ValueError):
            continue
        ids.append(sample_id)
        if row.get("value") not in (None, ""):
            value_count += 1
    return {
        "json_ok": True,
        "ids": ids,
        "value_count": value_count,
        "raw": content,
        "missing": sorted(set(expected_ids) - set(ids)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="豆包分栏样品识别临时验证")
    parser.add_argument("image", help="待测试图片路径")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise ValueError("找不到测试图片。")

    api_key, model, base_url = load_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)
    full_file_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    full_image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    layout_content = request_text(client, model, LAYOUT_PROMPT, full_file_type, full_image_base64)
    try:
        layout = json.loads(layout_content)
        print(f"布局分析 JSON 成功：是，rows_count：{layout.get('rows_count')}")
    except json.JSONDecodeError:
        print("布局分析 JSON 成功：否")
        print("布局分析原始输出：")
        print(layout_content)
        return

    all_ids: list[int] = []
    json_failures = 0
    all_missing: list[int] = []
    with Image.open(image_path) as source:
        for region_name, (box, expected_ids) in REGIONS.items():
            # 内存裁剪并旋正，避免将同编号的下方 K+ 页面混入本轮 Na+ 样品测试。
            region_image = source.crop(box).rotate(90, expand=True).convert("RGB")
            content = request_text(client, model, REGION_PROMPT, "image/png", encode_png(region_image))
            result = parse_region(content, expected_ids)
            if not result["json_ok"]:
                json_failures += 1
            all_ids.extend(result["ids"])
            all_missing.extend(result.get("missing", list(expected_ids)))
            print(
                f"{region_name}：JSON 成功={result['json_ok']}，"
                f"返回编号数={len(result['ids'])}，"
                f"非空数值数={result['value_count']}，"
                f"缺失编号={result.get('missing', list(expected_ids))}"
            )
            if not result["json_ok"]:
                print(f"{region_name} 原始输出：")
                print(result["raw"])

    unique_ids = sorted(set(all_ids))
    expected_all = set(range(1, 81))
    print(f"合并后编号数量：{len(unique_ids)}")
    print(f"合并后缺失编号：{sorted(expected_all - set(unique_ids))}")
    print(f"JSON 截断/解析失败区域数：{json_failures}")


if __name__ == "__main__":
    main()
