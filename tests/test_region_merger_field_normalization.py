"""局部区域字段标准化与顺序合并的离线测试。"""

from core.preprocessing.region_merger import merge_region_data_rows
from core.schemas import DataRow


def test_region_rows_are_normalized_without_sorting() -> None:
    merged = merge_region_data_rows(
        {
            "1-20": [
                DataRow(
                    values={"row_number": "20", "observed_value": "2.24"},
                    field_sources={"row_number": "original", "observed_value": "original"},
                    observed_values={"row_number": "20", "observed_value": "2.24"},
                )
            ],
            "21-40": [
                DataRow(
                    values={"left_num": "21", "right_val": "3.74"},
                    field_sources={"left_num": "original", "right_val": "original"},
                    observed_values={"left_num": "21", "right_val": "3.74"},
                ),
                DataRow(
                    values={"sample_id": "75", "value": None},
                    field_sources={"sample_id": "original", "value": "original"},
                    observed_values={"sample_id": "75", "value": None},
                ),
            ],
        }
    )

    assert [row.values for row in merged] == [
        {"row_number": "20", "observed_value": "2.24"},
        {"row_number": "21", "observed_value": "3.74"},
        {"row_number": "75", "observed_value": None},
    ]
    assert all(set(row.values) == {"row_number", "observed_value"} for row in merged)
