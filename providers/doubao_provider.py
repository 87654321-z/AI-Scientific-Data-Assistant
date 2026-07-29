"""火山方舟豆包视觉提供商。"""

import base64
import json
import os
import re
from copy import deepcopy

from dotenv import load_dotenv
from openai import OpenAI

from core.schemas import ColumnInfo, DataRow, ExperimentResult, SourceFile, UncertainItem
from prompts.local_region_pair_prompt import (
    LOCAL_REGION_PAIR_MODE,
    build_local_region_pair_prompt,
)
from prompts.scientific_data_prompt import build_scientific_data_prompt
from prompts.scientific_data_validation_prompt import build_scientific_data_validation_prompt
from providers.base_vision_provider import VisionProvider


class DoubaoProvider(VisionProvider):
    """通过火山方舟的 OpenAI 兼容接口调用单张图片理解模型。"""

    name = "doubao"

    _EXPLANATORY_PLACEHOLDER = re.compile(
        r"\[[^\]]*\b(?:stylized|unclear|unknown|character|symbol)\b[^\]]*\]",
        re.IGNORECASE,
    )
    _PLAIN_EXPLANATORY_TEXT = re.compile(
        r"\b(?:stylized\s+L|unclear\s+character|unknown\s+(?:character|symbol))\b",
        re.IGNORECASE,
    )
    _HALLUCINATED_TREATMENT_SEGMENT = re.compile(r"(?<=/)AXL(?=/|$)", re.IGNORECASE)
    _REPLICATE_METADATA_FIELDS = {"replicate_group", "replicate_index"}

    @staticmethod
    def _format_api_error(error: Exception) -> str:
        """把 OpenAI 兼容客户端的底层异常转换为可诊断的中文信息。"""
        response = getattr(error, "response", None)
        status_code = getattr(error, "status_code", None) or getattr(response, "status_code", None)
        request_id = getattr(error, "request_id", None)
        response_text = None
        if response is not None:
            headers = getattr(response, "headers", {}) or {}
            request_id = request_id or headers.get("x-request-id") or headers.get("request-id")
            try:
                response_text = response.text
            except Exception:
                response_text = None
        body = getattr(error, "body", None)
        message = getattr(error, "message", None) or str(error)

        category = {
            400: "请求参数、模型 ID 或图片格式可能有误",
            401: "API Key 无效或未授权",
            403: "账户或模型没有访问权限",
            404: "模型 ID 或接口地址不存在",
            429: "请求过于频繁、账户额度不足或余额不足",
        }.get(status_code, "网络、服务端或未知请求错误")

        details = [
            "豆包 API 请求失败。",
            f"错误类型：{type(error).__name__}",
            f"可能原因：{category}",
        ]
        if status_code is not None:
            details.append(f"HTTP 状态码：{status_code}")
        if message:
            details.append(f"错误信息：{message}")
        if body is not None:
            details.append(f"API 返回内容：{body}")
        elif response_text:
            details.append(f"API 返回内容：{response_text[:2000]}")
        if request_id:
            details.append(f"Request ID：{request_id}")
        return "\n".join(details)

    @classmethod
    def _sanitize_observed_value(cls, value, field_name: str | None = None):
        """移除模型的英文解释占位符，不把推理说明混入图片观察值。"""
        if not isinstance(value, str):
            return value
        sanitized = cls._EXPLANATORY_PLACEHOLDER.sub("[模糊字符]", value)
        sanitized = cls._PLAIN_EXPLANATORY_TEXT.sub("[模糊字符]", sanitized)
        # 仅在斜杠分段的处理编号中处理已知的模型补全片段，避免影响普通文本字段。
        if "/" in sanitized and (field_name is None or "treatment" in field_name.lower()):
            sanitized = cls._HALLUCINATED_TREATMENT_SEGMENT.sub("[模糊字符]", sanitized)
        return sanitized

    @staticmethod
    def _normalize_replicate_index(value) -> int | None:
        """将模型给出的重复序号安全转换为正整数；无法确认时保留为空。"""
        try:
            numeric_value = int(value)
        except (TypeError, ValueError):
            return None
        return numeric_value if numeric_value >= 1 else None

    def process_images(
        self,
        images: list[SourceFile],
        experiment_context: str | None = None,
    ) -> ExperimentResult:
        load_dotenv()
        api_key = os.getenv("ARK_API_KEY")
        model = os.getenv("ARK_MODEL")
        base_url = os.getenv(
            "ARK_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/v3",
        )
        if not api_key:
            raise ValueError("未配置 ARK_API_KEY。请在项目根目录的 .env 文件中设置它。")
        if not model:
            raise ValueError("未配置 ARK_MODEL。请在 .env 文件中填写豆包模型 ID 或推理接入点。")
        if len(images) != 1:
            raise ValueError("豆包测试模式当前只支持一张图片。")

        image = images[0]
        if image.file_type not in {"image/png", "image/jpeg", "image/jpg"}:
            raise ValueError("图片格式不支持。请上传 png、jpg 或 jpeg 图片。")
        if not image.content:
            raise ValueError("没有读取到图片内容。请重新上传图片后再试。")

        image_base64 = base64.b64encode(image.content).decode("ascii")
        is_local_region_pair_mode = experiment_context == LOCAL_REGION_PAIR_MODE
        prompt = (
            build_local_region_pair_prompt()
            if is_local_region_pair_mode
            else build_scientific_data_prompt(experiment_context)
        )
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )

        try:
            content = self._request_vision_text(client, model, prompt, image.file_type, image_base64)
            result = (
                self._to_local_region_pair_result(content, images)
                if is_local_region_pair_mode
                else self._to_experiment_result(content, images)
            )
            result.model_response_logs.append({"stage": "首次视觉识别", "content": content})
            if is_local_region_pair_mode:
                return result
            return self._add_validation_findings(
                client,
                model,
                image.file_type,
                image_base64,
                content,
                result,
            )
        except ValueError:
            raise
        except Exception as error:
            raise RuntimeError(self._format_api_error(error)) from error

    @staticmethod
    def _request_vision_text(
        client: OpenAI,
        model: str,
        prompt: str,
        file_type: str,
        image_base64: str,
    ) -> str:
        """发送图片和提示词，并返回模型的原始文本。"""
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{file_type};base64,{image_base64}"},
                    },
                ],
            }],
        )
        return response.choices[0].message.content or ""

    def _add_validation_findings(
        self,
        client: OpenAI,
        model: str,
        file_type: str,
        image_base64: str,
        first_pass_content: str,
        result: ExperimentResult,
    ) -> ExperimentResult:
        """执行只读二次检查；失败时保留首轮识别结果，不丢弃任何实验行。"""
        try:
            validation_prompt = build_scientific_data_validation_prompt(first_pass_content)
            validation_content = self._request_vision_text(
                client,
                model,
                validation_prompt,
                file_type,
                image_base64,
            )
            result.model_response_logs.append({"stage": "二次一致性校验", "content": validation_content})
            validation_data = json.loads(validation_content)
        except Exception as error:
            # 二次检查不能影响首轮已保留的数据；把问题写入警告供人工查看。
            result.model_response_logs.append({"stage": "二次一致性校验失败", "content": str(error)})
            result.warnings.append(f"二次 AI 校验未完成：{error}")
            return result

        additional_items = [
            self._to_uncertain_item(item, default_reason="二次 AI 校验发现需要确认的内容。")
            for item in validation_data.get("additional_uncertain_items", [])
        ]
        result.uncertain_items.extend(additional_items)
        result.warnings.extend(validation_data.get("warnings", []))
        return result

    @classmethod
    def _to_uncertain_item(cls, item: dict, default_reason: str) -> UncertainItem:
        """兼容模型直接字段和旧版 content 字段，保证页面仍可读取建议。"""
        raw_observed_value = item.get("observed_value")
        observed_value = cls._sanitize_observed_value(raw_observed_value, item.get("column_name"))
        suggested_value = item.get("suggested_value")
        confidence = item.get("confidence", "low")
        target_type = item.get("target_type", "cell")
        column_name = item.get("column_name")
        content = item.get("content") or (
            f"target_type={target_type}; "
            f"column_name={column_name if column_name is not None else 'null'}; "
            f"observed_value={observed_value if observed_value is not None else 'null'}; "
            f"suggested_value={suggested_value if suggested_value is not None else 'null'}; "
            f"confidence={confidence}"
        )
        # 只清理 content 的 observed_value 片段，不触碰 suggested_value。
        content = re.sub(
            r"(observed_value=)(.*?)(; suggested_value=)",
            lambda match: (
                f"{match.group(1)}{cls._sanitize_observed_value(match.group(2), item.get('column_name'))}"
                f"{match.group(3)}"
            ),
            content,
        )
        return UncertainItem(
            location=item.get("location", "未指定位置"),
            content=content,
            reason=item.get("reason") or item.get("basis") or default_reason,
        )

    def _to_experiment_result(
        self,
        content: str,
        images: list[SourceFile],
    ) -> ExperimentResult:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            stripped_content = content.rstrip()
            is_unclosed_json = bool(stripped_content) and not stripped_content.endswith(("}", "]"))
            error_near_end = error.pos >= max(0, len(content) - 5)
            if not stripped_content:
                truncation_diagnosis = "诊断：模型返回内容为空。"
            elif is_unclosed_json and error_near_end:
                truncation_diagnosis = (
                    "诊断：疑似模型输出在 JSON 闭合前被截断。"
                    f"解析在第 {error.pos} / {len(content)} 个字符附近失败，"
                    "末尾缺少 JSON 闭合符号。若内容很长，可能触及模型或接口的输出长度限制。"
                )
            else:
                truncation_diagnosis = (
                    "诊断：返回内容不是完整 JSON，但未检测到典型的末尾截断特征。"
                    f"JSON 解析错误：{error.msg}（第 {error.pos} / {len(content)} 个字符）。"
                )
            diagnostic_error = ValueError(
                "豆包返回内容不是有效 JSON，无法转换为结构化实验结果。"
                f"\n{truncation_diagnosis}"
                f"\n\n模型原始返回内容：\n{content}"
            )
            # 仅供页面开发期诊断读取；不参与 JSON 解析或业务数据处理。
            diagnostic_error.raw_content = content
            raise diagnostic_error from error

        columns = [
            ColumnInfo(
                internal_name=item["internal_name"],
                display_name=item.get("display_name", item["internal_name"]),
                unit=item.get("original_unit", item.get("unit")),
                confirmed=False,
                source="ai_suggestion",
                original_unit=item.get("original_unit", item.get("unit")),
                suggested_unit=item.get("suggested_unit"),
                final_unit=item.get("final_unit"),
            )
            for item in data.get("columns", [])
        ]
        observed_rows = data.get("observed_rows", data.get("ai_suggested_rows", data.get("rows", [])))
        observed_data_rows = []
        for row in observed_rows:
            values = {
                key: self._sanitize_observed_value(value, key)
                for key, value in row.items()
                if key not in self._REPLICATE_METADATA_FIELDS
            }
            observed_data_rows.append(
                DataRow(
                    values=values,
                    field_sources={key: "original" for key in values},
                    observed_values=deepcopy(values),
                    replicate_group=row.get("replicate_group"),
                    replicate_index=self._normalize_replicate_index(row.get("replicate_index")),
                )
            )
        uncertain_items = [
            self._to_uncertain_item(item, default_reason="模型无法确定。")
            for item in data.get("uncertain_items", [])
        ]
        return ExperimentResult(
            source_files=images,
            # 首轮输出不再要求 raw_text；模型即使意外返回该字段也不使用它。
            raw_text="",
            columns=columns,
            rows=deepcopy(observed_data_rows),
            ai_suggested_rows=deepcopy(observed_data_rows),
            uncertain_items=uncertain_items,
            warnings=data.get("warnings", []),
            provider=self.name,
        )

    def _to_local_region_pair_result(
        self,
        content: str,
        images: list[SourceFile],
    ) -> ExperimentResult:
        """把局部提示词的极简 pairs 结果转换为既有的 ExperimentResult。"""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            diagnostic_error = ValueError(
                "豆包局部区域返回内容不是有效 JSON，无法转换为编号-数值结果。"
                f"\n\n模型原始返回内容：\n{content}"
            )
            diagnostic_error.raw_content = content
            raise diagnostic_error from error

        rows = []
        for item in data.get("pairs", []):
            values = {
                "sample_id": item.get("sample_id"),
                "measurement_value": item.get("value"),
            }
            rows.append(
                DataRow(
                    values=values,
                    field_sources={key: "original" for key in values},
                    observed_values=deepcopy(values),
                )
            )

        return ExperimentResult(
            source_files=images,
            raw_text="",
            columns=[
                ColumnInfo("sample_id", "编号", None, False, "original"),
                ColumnInfo("measurement_value", "测量值", None, False, "original"),
            ],
            rows=deepcopy(rows),
            ai_suggested_rows=deepcopy(rows),
            uncertain_items=[],
            warnings=data.get("warnings", []),
            provider=self.name,
        )
