"""旋正图片的四栏边界调整临时验证。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "debug_preprocess"
ROTATED_IMAGE_PATH = OUTPUT_DIRECTORY / "rotated_image.png"
Y_START = 180
Y_END = 1160

# 第五阶段使用的旧边界：用于红色预览线核对。
CURRENT_COLUMNS = {
    "1-20": (120, 325),
    "21-40": (325, 530),
    "41-60": (530, 735),
    "61-80": (735, 940),
}

# 本次临时调整边界：每栏同时覆盖“编号列 + 紧邻数值列”。
# 后续人工核对时只需修改这里的 x 起止坐标。
ADJUSTED_COLUMNS = {
    "1-20": (250, 445),
    "21-40": (455, 650),
    "41-60": (660, 855),
    "61-80": (865, 1060),
}


def main() -> None:
    if not ROTATED_IMAGE_PATH.is_file():
        raise ValueError("找不到 rotated_image.png，请先运行第五阶段预处理脚本。")

    with Image.open(ROTATED_IMAGE_PATH) as source:
        image = source.convert("RGB")
        preview = image.copy()
        drawer = ImageDraw.Draw(preview)

        # 红线：旧边界；绿框：本次调整后的实际裁剪范围。
        for range_name, (x_start, x_end) in CURRENT_COLUMNS.items():
            drawer.line((x_start, Y_START, x_start, Y_END), fill="red", width=4)
            drawer.line((x_end, Y_START, x_end, Y_END), fill="red", width=4)
        for range_name, (x_start, x_end) in ADJUSTED_COLUMNS.items():
            drawer.rectangle((x_start, Y_START, x_end, Y_END), outline="lime", width=4)
            drawer.text((x_start + 3, Y_START + 3), range_name, fill="lime")

        preview_path = OUTPUT_DIRECTORY / "boundary_preview.png"
        preview.save(preview_path, format="PNG")
        print(f"旋正图尺寸：{image.size}")
        print(f"边界预览已保存：{preview_path}")

        for range_name, (x_start, x_end) in ADJUSTED_COLUMNS.items():
            box = (x_start, Y_START, x_end, Y_END)
            cropped = image.crop(box)
            output_path = OUTPUT_DIRECTORY / f"adjust_column_{range_name.replace('-', '_')}.png"
            cropped.save(output_path, format="PNG")
            print(f"adjust_column_{range_name.replace('-', '_')}.png 坐标：{box}")
            print(f"adjust_column_{range_name.replace('-', '_')}.png 尺寸：{cropped.size}")


if __name__ == "__main__":
    main()
