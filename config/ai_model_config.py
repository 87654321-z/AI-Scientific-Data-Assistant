"""统一读取用户、.env 和 Streamlit Cloud 的 AI 模型配置。"""

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION_CONFIG_KEY = "user_ai_model_config"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


@dataclass(frozen=True)
class AIModelConfig:
    """调用兼容 OpenAI 接口的视觉模型所需配置。"""

    api_key: str | None
    model: str | None
    base_url: str

    @property
    def is_complete(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)


def _clean(value) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _read_web_config() -> dict[str, str]:
    """读取当前网页会话中的配置；在非 Streamlit 环境中返回空字典。"""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is None:
            return {}
        return dict(st.session_state.get(SESSION_CONFIG_KEY, {}))
    except (ImportError, RuntimeError):
        return {}


def _read_streamlit_secrets() -> dict[str, str]:
    """读取 Streamlit Secrets；未配置 secrets.toml 时安静返回空字典。"""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is None:
            return {}
        return {
            key: value
            for key in ("ARK_API_KEY", "ARK_MODEL", "ARK_BASE_URL")
            if (value := st.secrets.get(key)) is not None
        }
    except (FileNotFoundError, ImportError, KeyError, RuntimeError):
        return {}


def get_ai_model_config() -> AIModelConfig:
    """按“网页输入 > 本地 .env/环境变量 > Streamlit Secrets”读取配置。"""
    web_config = _read_web_config()
    dotenv_config = dotenv_values(PROJECT_ROOT / ".env")
    secrets_config = _read_streamlit_secrets()

    def resolve(key: str) -> str | None:
        return (
            _clean(web_config.get(key))
            or _clean(dotenv_config.get(key))
            or _clean(os.getenv(key))
            or _clean(secrets_config.get(key))
        )

    return AIModelConfig(
        api_key=resolve("ARK_API_KEY"),
        model=resolve("ARK_MODEL"),
        base_url=resolve("ARK_BASE_URL") or DEFAULT_BASE_URL,
    )


def save_web_config(api_key: str, model: str, base_url: str) -> None:
    """仅在当前 Streamlit 会话中保存配置，不写入磁盘或日志。"""
    import streamlit as st

    st.session_state[SESSION_CONFIG_KEY] = {
        "ARK_API_KEY": api_key.strip(),
        "ARK_MODEL": model.strip(),
        "ARK_BASE_URL": base_url.strip(),
    }


def clear_web_config() -> None:
    """清除当前网页会话配置，使读取逻辑回退到环境配置。"""
    import streamlit as st

    st.session_state.pop(SESSION_CONFIG_KEY, None)
