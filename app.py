"""Scientific Data Assistant 的首页。"""

import streamlit as st


st.set_page_config(page_title="Scientific Data Assistant")


def show_home() -> None:
    """显示项目首页。"""
    st.title("Scientific Data Assistant")
    st.subheader("科学实验数据整理助手")

    st.write("本工具用于帮助科研人员和学生整理实验记录。")
    st.write("请从左侧菜单进入不同功能页面。")

    st.divider()
    st.write("当前版本：0.1")
    st.write("当前开发阶段：多页面框架")


selected_page = st.navigation(
    [
        st.Page(show_home, title="首页", default=True),
        st.Page("pages/1_Data_Upload.py", title="数据导入"),
        st.Page("pages/2_OCR.py", title="OCR 识别"),
        st.Page("pages/3_Data_Processing.py", title="数据整理"),
        st.Page("pages/4_Export.py", title="Excel 导出"),
        st.Page("pages/5_About.py", title="关于项目"),
        st.Page("pages/6_AI模型设置.py", title="AI 模型设置"),
    ]
)

selected_page.run()
