"""通过豆包兼容接口执行独立的结构化数据 Validation。"""

import json
import time
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI

from config.ai_model_config import get_ai_model_config
from core.schemas import ExperimentResult
from core.validation_schemas import (
    ValidationFinding,
    ValidationResult,
    ValidationRunLog,
)
from prompts.validation_prompt import build_validation_prompt
from providers.base_validation_provider import ValidationProvider


class DoubaoValidationProvider(ValidationProvider):
    """只检查已有结构化数据，不重新识别图片或修改原始数据。"""

    name = "doubao_validation"
    API_TIMEOUT_SECONDS = 180.0
    _JSON_RETRY_INSTRUCTION = (
        "\n\n上一结果不是可解析的完整 JSON。请只返回完整 JSON，不要 Markdown、解释或输入副本。"
    )
    _ISSUE_TYPES = {
        "missing_value",
        "type_mismatch",
        "identifier_pattern",
        "unit_inconsistency",
        "replicate_inconsistency",
        "numeric_format",
        "possible_outlier",
        "unresolved_character",
        "other",
    }
    _SCOPES = {"cell", "row", "column", "global"}
    _CONFIDENCE_LEVELS = {"low", "medium", "high"}
    _SEVERITY_LEVELS = {"low", "medium", "high"}
    _LOCATION_STATUSES = {
        "unvalidated",
        "resolved",
        "unresolved",
        "ambiguous",
        "unknown",
    }

    def validate_result(
        self,
        experiment_result: ExperimentResult,
        experiment_context: str | None = None,
    ) -> ValidationResult:
        total_started_at = time.perf_counter()
        config = get_ai_model_config()
        run_log = ValidationRunLog(
            provider=self.name,
            model=config.model or "",
        )
        if not config.api_key:
            raise ValueError("未配置 API Key，无法执行 AI 数据检查。")
        if not config.model:
            raise ValueError("未配置 Model ID，无法执行 AI 数据检查。")

        prompt = build_validation_prompt(experiment_result, experiment_context)
        client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=self.API_TIMEOUT_SECONDS,
            max_retries=0,
        )

        try:
            attempts: list[dict[str, Any]] = []
            content = self._request_text(client, config.model, prompt, attempts)
            try:
                result = self._parse_result(content)
            except ValueError as first_error:
                retry_content = self._request_text(
                    client,
                    config.model,
                    prompt + self._JSON_RETRY_INSTRUCTION,
                    attempts,
                )
                content = retry_content
                try:
                    result = self._parse_result(retry_content)
                except ValueError as retry_error:
                    finish_reason = attempts[-1].get("finish_reason", "")
                    category = (
                        "输出截断" if finish_reason == "length" else "JSON 解析错误"
                    )
                    raise ValueError(
                        f"AI 数据检查{category}：连续两次没有返回完整、有效的 JSON。"
                        f"首次错误：{first_error}；重试错误：{retry_error}"
                    ) from retry_error

            self._finish_run_log(
                run_log,
                total_started_at,
                success=True,
                raw_response=content,
                api_key=config.api_key,
            )
            result.provider = self.name
            result.response_metadata = {"attempts": attempts}
            result.run_log = run_log
            return result
        except Exception as error:
            self._finish_run_log(
                run_log,
                total_started_at,
                success=False,
                error=error,
                raw_response=locals().get("content", ""),
                api_key=config.api_key,
            )
            setattr(error, "validation_run_log", run_log)
            raise

    @classmethod
    def _request_text(
        cls,
        client: OpenAI,
        model: str,
        prompt: str,
        attempts: list[dict[str, Any]],
    ) -> str:
        started_at = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as error:
            elapsed = time.perf_counter() - started_at
            attempts.append({
                "response_id": "",
                "finish_reason": "",
                "token_usage": {},
                "output_length": 0,
                "api_elapsed_seconds": round(elapsed, 3),
                "success": False,
                "error_category": cls._error_category(error),
            })
            raise RuntimeError(cls._format_api_error(error)) from error

        elapsed = time.perf_counter() - started_at
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = getattr(response, "usage", None)
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        attempts.append({
            "response_id": str(getattr(response, "id", "") or ""),
            "finish_reason": str(getattr(choice, "finish_reason", "") or ""),
            "token_usage": usage if isinstance(usage, dict) else {},
            "output_length": len(content),
            "api_elapsed_seconds": round(elapsed, 3),
        })
        return content

    @classmethod
    def _parse_result(cls, content: str) -> ValidationResult:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"返回内容不是有效 JSON：{error.msg}") from error
        if not isinstance(data, dict):
            raise ValueError("Validation 顶层结果必须是 JSON 对象。")

        warnings = data.get("warnings", [])
        suggestions = data.get("suggestions", [])
        uncertain_items = data.get("uncertain_items", [])
        if not isinstance(warnings, list):
            raise ValueError("warnings 必须是列表。")
        if not isinstance(suggestions, list):
            raise ValueError("suggestions 必须是列表。")
        if not isinstance(uncertain_items, list):
            raise ValueError("uncertain_items 必须是列表。")

        return ValidationResult(
            warnings=[str(item) for item in warnings],
            suggestions=[
                cls._parse_finding(item, index, "suggestion")
                for index, item in enumerate(suggestions, start=1)
            ],
            uncertain_items=[
                cls._parse_finding(item, index, "uncertain")
                for index, item in enumerate(uncertain_items, start=1)
            ],
            provider=cls.name,
            status="completed",
        )

    @classmethod
    def _parse_finding(
        cls,
        item: Any,
        index: int,
        prefix: str,
    ) -> ValidationFinding:
        if not isinstance(item, dict):
            raise ValueError("每个 Validation finding 必须是 JSON 对象。")
        row_index = item.get("row_index")
        if row_index is not None:
            try:
                row_index = int(row_index)
            except (TypeError, ValueError) as error:
                raise ValueError("row_index 必须是整数或 null。") from error
        scope = str(item.get("scope") or "cell")
        issue_type = str(item.get("issue_type") or "other")
        confidence = str(item.get("confidence") or "low")
        severity = str(item.get("severity") or "medium")
        location_status = str(item.get("location_status") or "unvalidated")
        return ValidationFinding(
            finding_id=str(item.get("finding_id") or f"{prefix}-{index:04d}"),
            scope=scope if scope in cls._SCOPES else "global",
            row_index=row_index,
            column_name=(
                str(item["column_name"])
                if item.get("column_name") is not None
                else None
            ),
            observed_value=item.get("observed_value"),
            issue_type=(issue_type if issue_type in cls._ISSUE_TYPES else "other"),
            reason=str(item.get("reason") or "需要人工检查。"),
            suggested_value=item.get("suggested_value"),
            confidence=(
                confidence if confidence in cls._CONFIDENCE_LEVELS else "low"
            ),
            severity=(severity if severity in cls._SEVERITY_LEVELS else "medium"),
            location_status=(
                location_status
                if location_status in cls._LOCATION_STATUSES
                else "unvalidated"
            ),
        )

    @classmethod
    def _finish_run_log(
        cls,
        run_log: ValidationRunLog,
        started_at: float,
        *,
        success: bool,
        raw_response: str,
        api_key: str,
        error: Exception | None = None,
    ) -> None:
        """完成运行日志；密钥无论来自响应还是异常都必须被遮蔽。"""
        run_log.finished_at = datetime.now(timezone.utc).isoformat()
        run_log.elapsed_seconds = round(time.perf_counter() - started_at, 3)
        run_log.success = success
        run_log.raw_response = cls._redact_secret(raw_response, api_key)
        if error is not None:
            run_log.error_category = cls._error_category(error)
            run_log.error_message = cls._redact_secret(str(error), api_key)

    @staticmethod
    def _redact_secret(value: str, secret: str) -> str:
        text = str(value or "")
        return text.replace(secret, "[REDACTED]") if secret else text

    @classmethod
    def _error_category(cls, error: Exception) -> str:
        """提供稳定的错误分类，避免依赖用户可见的自然语言。"""
        cause = error.__cause__
        error_type = type(cause or error).__name__
        if error_type in {
            "APITimeoutError",
            "TimeoutException",
            "ReadTimeout",
            "ConnectTimeout",
            "TimeoutError",
        }:
            return "timeout"
        if error_type in {"APIConnectionError", "ConnectError"}:
            return "network"
        if isinstance(error, ValueError):
            return "output_truncated" if "输出截断" in str(error) else "json_parse"
        if getattr(cause or error, "status_code", None) is not None:
            return "api_error"
        return "api_error"

    @classmethod
    def _format_api_error(cls, error: Exception) -> str:
        error_type = type(error).__name__
        if error_type in {
            "APITimeoutError",
            "TimeoutException",
            "ReadTimeout",
            "ConnectTimeout",
            "TimeoutError",
        }:
            return (
                f"AI 数据检查请求超时：模型在 {cls.API_TIMEOUT_SECONDS:g} 秒内没有返回结果，"
                "请稍后重试。"
            )
        if error_type in {"APIConnectionError", "ConnectError"}:
            return "AI 数据检查网络连接失败，请检查网络和 Base URL。"
        status_code = getattr(error, "status_code", None)
        message = getattr(error, "message", None) or str(error)
        status_text = f"HTTP 状态码 {status_code}；" if status_code is not None else ""
        return f"AI 数据检查 API 调用失败：{status_text}{message}"
