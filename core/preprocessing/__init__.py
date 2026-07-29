"""已验证的本地图像预处理辅助模块。

当前模块尚未接入正式 OCR 流程，仅供临时实验和后续集成使用。
"""

from core.preprocessing.layout_detector import detect_large_image_layout
from core.preprocessing.region_merger import (
    merge_region_data_rows,
    merge_region_rows,
    normalize_region_data_row,
)
from core.preprocessing.region_splitter import VERIFIED_COLUMN_BOXES, split_verified_columns
from core.preprocessing.rotation import rotate_record_image

__all__ = [
    "VERIFIED_COLUMN_BOXES",
    "detect_large_image_layout",
    "merge_region_data_rows",
    "merge_region_rows",
    "normalize_region_data_row",
    "rotate_record_image",
    "split_verified_columns",
]
