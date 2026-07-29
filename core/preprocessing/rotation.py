"""科研记录图片的本地方向处理。"""

from PIL import Image, ImageOps


def rotate_record_image(image: Image.Image) -> tuple[Image.Image, int]:
    """按 EXIF 校正方向，并将纵向记录照片逆时针旋正为横向阅读方向。

    返回旋正后的 RGB 图片和本次额外旋转角度。该函数不保存文件。
    """
    corrected = ImageOps.exif_transpose(image).convert("RGB")
    if corrected.height > corrected.width:
        return corrected.rotate(90, expand=True), 90
    return corrected, 0
