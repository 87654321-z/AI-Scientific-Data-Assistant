"""已验证四栏图片的灰度预处理工作流。

该模块尚未改变任何 VisionProvider 接口；它仅把内存中的裁剪图逐一交给
现有 Provider，再合并其原有 ExperimentResult 数据。
"""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.preprocessing.region_merger import merge_region_data_rows
from core.preprocessing.region_splitter import split_verified_columns
from core.preprocessing.rotation import rotate_record_image
from core.schemas import ColumnInfo, ExperimentResult, SourceFile
from prompts.local_region_pair_prompt import LOCAL_REGION_PAIR_MODE
from providers.base_vision_provider import VisionProvider


def process_verified_preprocessed_image(
    images: list[SourceFile],
    provider: VisionProvider,
    experiment_context: str | None = None,
) -> ExperimentResult:
    """旋正、切分四栏、逐栏调用现有 Provider 并合并结果。

    仅支持一张具备已验证布局的图片。所有裁剪图仅存于内存，最终结果仍关联原始图片。
    """
    if len(images) != 1:
        raise ValueError("预处理灰度测试当前只支持上传一张图片。")
    source_file = images[0]
    if not source_file.content:
        raise ValueError("没有读取到图片内容，无法执行预处理。")

    try:
        with Image.open(BytesIO(source_file.content)) as source_image:
            rotated_image, rotation_angle = rotate_record_image(source_image)
            region_images = split_verified_columns(rotated_image)
    except OSError as error:
        raise ValueError("图片无法读取，无法执行预处理。") from error

    region_results: dict[str, ExperimentResult] = {}
    image_stem = Path(source_file.filename).stem
    for range_name, region_image in region_images.items():
        buffer = BytesIO()
        region_image.save(buffer, format="PNG")
        region_file = SourceFile(
            filename=f"{image_stem}_{range_name}.png",
            file_type="image/png",
            content=buffer.getvalue(),
        )
        # 局部区域不是通用表格：使用编号-数值对专用模式，避免模型创建 col1/col2 等列。
        region_results[range_name] = provider.process_images([region_file], LOCAL_REGION_PAIR_MODE)

    merged_rows = merge_region_data_rows(
        {range_name: result.rows for range_name, result in region_results.items()}
    )
    merged_suggested_rows = merge_region_data_rows(
        {range_name: result.ai_suggested_rows for range_name, result in region_results.items()}
    )
    warnings = [
        f"预处理灰度测试已启用：图片逆时针旋转 {rotation_angle}°，并按四栏分别识别后合并。"
    ]
    uncertain_items = []
    model_response_logs = []
    for range_name, result in region_results.items():
        warnings.extend(result.warnings)
        uncertain_items.extend(deepcopy(result.uncertain_items))
        model_response_logs.extend(
            {
                "stage": f"预处理区域 {range_name}：{log['stage']}",
                "content": log["content"],
            }
            for log in result.model_response_logs
        )

    return ExperimentResult(
        source_files=images,
        raw_text="",
        columns=[
            ColumnInfo("row_number", "编号", None, False, "original"),
            ColumnInfo("observed_value", "测量值", None, False, "original"),
        ],
        rows=merged_rows,
        ai_suggested_rows=merged_suggested_rows,
        uncertain_items=uncertain_items,
        warnings=warnings,
        provider=next(iter(region_results.values())).provider,
        model_response_logs=model_response_logs,
    )
