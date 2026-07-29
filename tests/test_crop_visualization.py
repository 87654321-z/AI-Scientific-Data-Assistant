"""导出第二阶段区域识别使用的临时裁剪图，供人工核对。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_doubao_region_recognition import REGIONS


OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "debug_crops"
OUTPUT_FILENAMES = {
    "区域1（1-20）": "region_1_20.png",
    "区域2（21-40）": "region_21_40.png",
    "区域3（41-60）": "region_41_60.png",
    "区域4（61-80）": "region_61_80.png",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="导出临时区域裁剪图")
    parser.add_argument("image", help="原始图片路径")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise ValueError("找不到原始图片。")

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        print(f"原图尺寸：{source.size}")
        for region_name, (box, _) in REGIONS.items():
            # 与第二阶段脚本一致：使用相同坐标裁剪，再旋正为模型实际输入方向。
            cropped = source.crop(box).rotate(90, expand=True).convert("RGB")
            output_path = OUTPUT_DIRECTORY / OUTPUT_FILENAMES[region_name]
            print(f"{region_name} 裁剪区域坐标：{box}")
            print(f"{region_name} 裁剪后尺寸：{cropped.size}")
            cropped.save(output_path, format="PNG")
            print(f"{region_name} 已保存：{output_path}")


if __name__ == "__main__":
    main()
