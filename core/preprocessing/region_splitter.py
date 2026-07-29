"""已验证的80样品记录四栏固定切分坐标。"""

from PIL import Image


# 坐标基于第五、六阶段验证后的旋正图（2275 x 1279），只覆盖上方 Na+ 页面。
VERIFIED_COLUMN_BOXES: dict[str, tuple[int, int, int, int]] = {
    "1-20": (250, 180, 445, 1160),
    "21-40": (455, 180, 650, 1160),
    "41-60": (660, 180, 855, 1160),
    "61-80": (865, 180, 1060, 1160),
}


def split_verified_columns(image: Image.Image) -> dict[str, Image.Image]:
    """按已验证坐标切分旋正后的四个编号栏位。

    图片尺寸不足时直接报错，避免静默产生错误裁剪图。函数不保存文件。
    """
    width, height = image.size
    maximum_x = max(box[2] for box in VERIFIED_COLUMN_BOXES.values())
    maximum_y = max(box[3] for box in VERIFIED_COLUMN_BOXES.values())
    if width < maximum_x or height < maximum_y:
        raise ValueError(
            f"旋正图片尺寸不足：当前为 {image.size}，至少需要 ({maximum_x}, {maximum_y})。"
        )
    return {
        range_name: image.crop(box).copy()
        for range_name, box in VERIFIED_COLUMN_BOXES.items()
    }
