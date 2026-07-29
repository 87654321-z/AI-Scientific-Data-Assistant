"""四个已切分栏位的豆包数字识别临时验证。"""

from __future__ import annotations

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


INPUT_DIRECTORY = Path(__file__).resolve().parent / "debug_preprocess"
REGIONS = {
    "区域1（1-20）": (INPUT_DIRECTORY / "adjust_column_1_20.png", range(1, 21)),
    "区域2（21-40）": (INPUT_DIRECTORY / "adjust_column_21_40.png", range(21, 41)),
    "区域3（41-60）": (INPUT_DIRECTORY / "adjust_column_41_60.png", range(41, 61)),
    "区域4（61-80）": (INPUT_DIRECTORY / "adjust_column_61_80.png", range(61, 81)),
}

REGION_PROMPT = """你是一名科研实验记录数字识别助手。请识别图片中的编号和值。
图片中每个编号对应一个测量值。

只返回一个有效 JSON 对象，不要 Markdown、解释文字或任何其他字段：
{
  "rows": [
    {"sample_id": "图片中的编号", "value": "图片中直接看到的数值或null"}
  ]
}

sample_id 保留图片中的编号；value 保留图片中直接看到的数值。
不推理、不补全；看不清填写 null。
禁止输出 raw_text、uncertain_items、suggested_value、warnings、columns 或其他字段。"""


def load_settings() -> tuple[str, str, str]:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ARK_API_KEY")
    model = os.getenv("ARK_MODEL")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    if not api_key or not model:
        raise ValueError("未读取到 ARK_API_KEY 或 ARK_MODEL。")
    return api_key, model, base_url


def request_region(client: OpenAI, model: str, image_path: Path) -> tuple[bool, list[dict], str]:
    if not image_path.is_file():
        raise ValueError(f"找不到局部图片：{image_path}")
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    content = DoubaoProvider()._request_vision_text(
        client, model, REGION_PROMPT, "image/png", image_base64
    )
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return False, [], content
    rows = data.get("rows", [])
    return True, rows if isinstance(rows, list) else [], content


def parse_ids(rows: list[dict]) -> list[int]:
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            ids.append(int(row.get("sample_id")))
        except (TypeError, ValueError):
            continue
    return ids


def main() -> None:
    api_key, model, base_url = load_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)
    all_ids: list[int] = []
    failed_regions = 0

    for region_name, (image_path, expected_ids) in REGIONS.items():
        json_ok, rows, raw_content = request_region(client, model, image_path)
        ids = parse_ids(rows)
        missing = sorted(set(expected_ids) - set(ids))
        all_ids.extend(ids)
        print(f"{region_name} JSON 解析成功：{json_ok}")
        print(f"{region_name} rows 数量：{len(rows)}")
        print(f"{region_name} sample_id 列表：{ids}")
        print(f"{region_name} 缺失编号：{missing}")
        print(f"{region_name} 数值识别结果：{json.dumps(rows, ensure_ascii=False)}")
        if not json_ok:
            failed_regions += 1
            print(f"{region_name} 模型原始输出：")
            print(raw_content)

    unique_ids = sorted(set(all_ids))
    duplicates = sorted({sample_id for sample_id in all_ids if all_ids.count(sample_id) > 1})
    expected_all = set(range(1, 81))
    print(f"合并后唯一编号数量：{len(unique_ids)}")
    print(f"是否达到80：{len(unique_ids) == 80}")
    print(f"重复编号：{duplicates}")
    print(f"缺失编号：{sorted(expected_all - set(unique_ids))}")
    print(f"JSON 解析失败区域数：{failed_regions}")


if __name__ == "__main__":
    main()
