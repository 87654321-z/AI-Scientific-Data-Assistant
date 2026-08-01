"""Doubao Validation Provider 的离线协议测试。"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config.ai_model_config import AIModelConfig
from core.schemas import ColumnInfo, DataRow, ExperimentResult
from providers.doubao_validation_provider import DoubaoValidationProvider


def make_result() -> ExperimentResult:
    return ExperimentResult(
        source_files=[],
        raw_text="",
        columns=[ColumnInfo("treatment_id", "处理编号", None, False, "original")],
        rows=[DataRow(
            values={"treatment_id": "S0/AH/E+/N2"},
            field_sources={"treatment_id": "original"},
            observed_values={"treatment_id": "S0/AH/E+/N2"},
        )],
        ai_suggested_rows=[],
        uncertain_items=[],
        warnings=[],
        provider="test",
    )


VALID_RESPONSE = json.dumps({
    "warnings": [],
    "suggestions": [{
        "finding_id": "validation-0001",
        "scope": "cell",
        "row_index": 1,
        "column_name": "treatment_id",
        "observed_value": "S0/AH/E+/N2",
        "issue_type": "identifier_pattern",
        "reason": "第二分段与其他记录不一致。",
        "suggested_value": "S0/H/E+/N2",
        "confidence": "low",
    }],
    "uncertain_items": [],
}, ensure_ascii=False)


class FakeCompletions:
    responses = []
    error = None
    calls = []

    def create(self, **kwargs):
        type(self).calls.append(kwargs)
        if type(self).error is not None:
            raise type(self).error
        content = type(self).responses.pop(0)
        return SimpleNamespace(
            id="validation-response",
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content),
            )],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )


class FakeOpenAI:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=FakeCompletions())
        type(self).instances.append(self)


class APITimeoutError(Exception):
    pass


class APIStatusError(Exception):
    status_code = 500


class DoubaoValidationProviderTests(unittest.TestCase):
    def setUp(self):
        FakeCompletions.responses = []
        FakeCompletions.error = None
        FakeCompletions.calls = []
        FakeOpenAI.instances = []
        self.config = AIModelConfig("secret-test-key", "test-model", "https://example.invalid/v1")

    def test_valid_json_is_converted_to_validation_result(self):
        FakeCompletions.responses = [VALID_RESPONSE]
        with patch(
            "providers.doubao_validation_provider.get_ai_model_config",
            return_value=self.config,
        ), patch(
            "providers.doubao_validation_provider.OpenAI",
            FakeOpenAI,
        ):
            result = DoubaoValidationProvider().validate_result(make_result())

        self.assertEqual(len(result.suggestions), 1)
        self.assertEqual(result.suggestions[0].suggested_value, "S0/H/E+/N2")
        self.assertEqual(len(result.response_metadata["attempts"]), 1)
        self.assertEqual(FakeOpenAI.instances[0].kwargs["timeout"], 180.0)
        self.assertEqual(FakeOpenAI.instances[0].kwargs["max_retries"], 0)

    def test_invalid_json_retries_once(self):
        FakeCompletions.responses = ["{not-complete", VALID_RESPONSE]
        with patch(
            "providers.doubao_validation_provider.get_ai_model_config",
            return_value=self.config,
        ), patch(
            "providers.doubao_validation_provider.OpenAI",
            FakeOpenAI,
        ):
            result = DoubaoValidationProvider().validate_result(make_result())

        self.assertEqual(len(FakeCompletions.calls), 2)
        self.assertEqual(len(result.response_metadata["attempts"]), 2)

    def test_timeout_has_clear_message_and_no_key(self):
        FakeCompletions.error = APITimeoutError("timed out")
        with patch(
            "providers.doubao_validation_provider.get_ai_model_config",
            return_value=self.config,
        ), patch(
            "providers.doubao_validation_provider.OpenAI",
            FakeOpenAI,
        ):
            with self.assertRaises(RuntimeError) as captured:
                DoubaoValidationProvider().validate_result(make_result())

        message = str(captured.exception)
        self.assertIn("请求超时", message)
        self.assertIn("180", message)
        self.assertNotIn("secret-test-key", message)

    def test_api_failure_has_clear_message_and_no_key(self):
        FakeCompletions.error = APIStatusError("service unavailable")
        with patch(
            "providers.doubao_validation_provider.get_ai_model_config",
            return_value=self.config,
        ), patch(
            "providers.doubao_validation_provider.OpenAI",
            FakeOpenAI,
        ):
            with self.assertRaises(RuntimeError) as captured:
                DoubaoValidationProvider().validate_result(make_result())

        message = str(captured.exception)
        self.assertIn("API 调用失败", message)
        self.assertIn("500", message)
        self.assertNotIn("secret-test-key", message)

    def test_api_failure_attaches_safe_run_log(self):
        FakeCompletions.error = APIStatusError("service unavailable secret-test-key")
        with patch(
            "providers.doubao_validation_provider.get_ai_model_config",
            return_value=self.config,
        ), patch(
            "providers.doubao_validation_provider.OpenAI",
            FakeOpenAI,
        ):
            with self.assertRaises(RuntimeError) as captured:
                DoubaoValidationProvider().validate_result(make_result())

        run_log = captured.exception.validation_run_log
        self.assertFalse(run_log.success)
        self.assertEqual(run_log.provider, "doubao_validation")
        self.assertEqual(run_log.model, "test-model")
        self.assertEqual(run_log.error_category, "api_error")
        self.assertIsNotNone(run_log.finished_at)
        self.assertGreaterEqual(run_log.elapsed_seconds, 0)
        self.assertNotIn("secret-test-key", run_log.error_message)

    def test_raw_response_is_logged_without_api_key(self):
        response_with_secret = VALID_RESPONSE.replace(
            '"warnings": []',
            '"warnings": ["secret-test-key"]',
        )
        FakeCompletions.responses = [response_with_secret]
        with patch(
            "providers.doubao_validation_provider.get_ai_model_config",
            return_value=self.config,
        ), patch(
            "providers.doubao_validation_provider.OpenAI",
            FakeOpenAI,
        ):
            result = DoubaoValidationProvider().validate_result(make_result())

        self.assertTrue(result.run_log.success)
        self.assertNotIn("secret-test-key", result.run_log.raw_response)
        self.assertIn("[REDACTED]", result.run_log.raw_response)


if __name__ == "__main__":
    unittest.main()
