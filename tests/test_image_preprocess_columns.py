"""80 样品图片的旋正与固定四栏切分临时验证。"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "debug_preprocess"


def main() -> None:
    parser = argparse.ArgumentParser(description="旋正并切分80样品记录四栏")
    parser.add_argument("image", help="原始图片路径")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise ValueError("找不到原始图片。")

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        original_size = source.size
        image = ImageOps.exif_transpose(source).convert("RGB")
        rotation_angle = 0
        # 这类记录本应横向阅读。纵向照片没有可靠 EXIF 时，固定逆时针旋转90°。
        if image.height > image.width:
            image = image.rotate(90, expand=True)
            rotation_angle = 90

        rotated_path = OUTPUT_DIRECTORY / "rotated_image.png"
        image.save(rotated_path, format="PNG")

        # 坐标基于旋正后的 2275 x 1279 图片：只选择上方 Na+ 页面的完整四栏。
        column_boxes = {
            "column_1_20.png": (120, 180, 325, 1160),
            "column_21_40.png": (325, 180, 530, 1160),
            "column_41_60.png": (530, 180, 735, 1160),
            "column_61_80.png": (735, 180, 940, 1160),
        }

        print(f"原图尺寸：{original_size}")
        print(f"旋转角度：逆时针 {rotation_angle}°")
        print(f"旋转后尺寸：{image.size}")
        print(f"旋正图已保存：{rotated_path}")
        for filename, box in column_boxes.items():
            cropped = image.crop(box)
            output_path = OUTPUT_DIRECTORY / filename
            cropped.save(output_path, format="PNG")
            print(f"{filename} 裁剪区域坐标：{box}")
            print(f"{filename} 裁剪后尺寸：{cropped.size}")


if __name__ == "__main__":
    main()
