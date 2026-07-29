"""局部编号-数值对提示词与解析的最小离线测试。"""

from providers.doubao_provider import DoubaoProvider
from prompts.local_region_pair_prompt import build_local_region_pair_prompt
from core.schemas import SourceFile


def test_local_prompt_is_pair_only() -> None:
    prompt = build_local_region_pair_prompt()
    assert '"pairs"' in prompt
    assert '"sample_id"' in prompt
    assert '"value"' in prompt
    assert "不要 Markdown、解释文字、columns" in prompt
    assert '禁止删除该编号' in prompt


def test_local_pair_result_converts_to_existing_result() -> None:
    content = '{"pairs":[{"sample_id":"1","value":"2.72"},{"sample_id":"2","value":null}],"warnings":[]}'
    source = SourceFile("region.png", "image/png", b"image")

    result = DoubaoProvider()._to_local_region_pair_result(content, [source])

    assert [row.values for row in result.rows] == [
        {"sample_id": "1", "measurement_value": "2.72"},
        {"sample_id": "2", "measurement_value": None},
    ]
    assert [column.internal_name for column in result.columns] == [
        "sample_id",
        "measurement_value",
    ]
