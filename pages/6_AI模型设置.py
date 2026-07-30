"""用户自己的 AI 视觉模型配置页面。"""

import streamlit as st

from config.ai_model_config import (
    DEFAULT_BASE_URL,
    SESSION_CONFIG_KEY,
    clear_web_config,
    get_ai_model_config,
    save_web_config,
)


st.title("AI 模型设置")
st.write("配置你自己的视觉模型。配置只保存在当前网页会话中，不会写入项目文件或数据库。")
st.warning("请勿在截图、Issue 或公开聊天中展示 API Key。模型调用可能产生费用。")

current_web_config = st.session_state.get(SESSION_CONFIG_KEY, {})
current_config = get_ai_model_config()

with st.form("ai_model_settings_form"):
    api_key = st.text_input(
        "API Key",
        value=current_web_config.get("ARK_API_KEY", ""),
        type="password",
        placeholder="请输入你自己的 API Key",
    )
    model = st.text_input(
        "Model ID",
        value=current_web_config.get("ARK_MODEL", ""),
        placeholder="请输入模型 ID 或推理接入点",
    )
    base_url = st.text_input(
        "Base URL",
        value=current_web_config.get("ARK_BASE_URL", DEFAULT_BASE_URL),
        placeholder=DEFAULT_BASE_URL,
    )
    saved = st.form_submit_button("保存到当前会话", type="primary")

if saved:
    if not api_key.strip() or not model.strip() or not base_url.strip():
        st.error("API Key、Model ID 和 Base URL 都需要填写。")
    else:
        save_web_config(api_key, model, base_url)
        st.success("配置已保存到当前网页会话。现在可以进入“OCR 识别”页面测试。")

if st.button("清除网页配置"):
    clear_web_config()
    st.success("网页配置已清除。系统将使用 .env 或 Streamlit Cloud Secrets。")

st.subheader("Base URL 示例")
st.code(
    "豆包 Ark:\n"
    "https://ark.cn-beijing.volces.com/api/v3\n\n"
    "OpenAI:\n"
    "https://api.openai.com/v1"
)

st.subheader("当前状态")
if current_web_config:
    st.info("当前优先使用：网页会话配置")
elif current_config.is_complete:
    st.info("当前已从本地环境或 Streamlit Cloud Secrets 读取到完整配置。")
else:
    st.warning("尚未配置完整的 API Key 和 Model ID。页面可以正常使用，但不能调用真实视觉模型。")
