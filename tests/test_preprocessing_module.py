"""不调用 API 的预处理模块最小验证。"""

from PIL import Image

from core.preprocessing import (
    VERIFIED_COLUMN_BOXES,
    merge_region_rows,
    rotate_record_image,
    split_verified_columns,
)


def test_rotation_and_split_dimensions() -> None:
    source = Image.new("RGB", (1279, 2275), "white")
    rotated, angle = rotate_record_image(source)
    assert angle == 90
    assert rotated.size == (2275, 1279)

    columns = split_verified_columns(rotated)
    assert set(columns) == set(VERIFIED_COLUMN_BOXES)
    assert all(column.size == (195, 980) for column in columns.values())


def test_merge_matches_current_local_test_coverage() -> None:
    # 第七阶段实测只缺少40号；本测试只验证合并规则，不调用模型。
    region_results = {
        "1-20": [{"sample_id": str(index), "value": str(index)} for index in range(1, 21)],
        "21-40": [{"sample_id": str(index), "value": str(index)} for index in range(21, 40)],
        "41-60": [{"sample_id": str(index), "value": str(index)} for index in range(41, 61)],
        "61-80": [{"sample_id": str(index), "value": str(index)} for index in range(61, 81)],
    }
    merged = merge_region_rows(region_results)
    merged_ids = [int(row["sample_id"]) for row in merged]
    assert len(merged) == 79
    assert merged_ids == [*range(1, 40), *range(41, 81)]
