# AI Scientific Data Assistant

> v0.1 · 面向科研实验记录的结构化整理与人工确认工具

AI Scientific Data Assistant 用于将实验记录图片、Word 文档和表格文件整理为可检查的结构化数据，并导出 Excel。它的设计重点不是让 AI 直接替代科研人员，而是保留原始识别内容、标出不确定项，并让用户确认最终数据。

## 当前支持

- Streamlit 多页面网页界面。
- 上传与预览 PNG、JPG、JPEG、CSV、XLSX、DOCX 文件。
- EasyOCR 本地基础文字识别与人工校对。
- 基于火山引擎 Ark 的 Doubao Vision 单图科研记录识别。
- AI 建议确认：保留原始观察值、AI 建议值和用户最终确认值的来源区别。
- 不确定项提示、人工保留/采用建议/手动修改。
- 导出包含“整理后数据”“字段说明”“识别记录”的 XLSX 文件。
- 面向已验证的横向四栏大图，提供可选的旋正、区域切分和局部编号-数值对识别实验流程。

## 工作流

```text
上传实验图片或文件
        ↓
AI 视觉识别或本地基础 OCR
        ↓
结构化数据与不确定项
        ↓
人工确认或修改
        ↓
导出 Excel
```

核心原则：

- `observed_value`：图片中直接观察到的内容。
- `suggested_value`：AI 根据上下文给出的候选建议。
- `final_value`：用户确认后用于导出的内容。
- AI 建议不会自动覆盖原始观察值或最终确认值。
- 缺失和不确定数据会被保留或标记，不应伪装成真实测量数据。

## 技术架构

```text
pages/       Streamlit 页面与用户交互
core/        数据模型、确认服务、Excel 导出、预处理
providers/   统一 VisionProvider 接口与模型实现
prompts/     与模型无关的科研识别提示词
tests/       本地测试与临时验证脚本
```

网页、未来的命令行工具或其他 AI 平台适配层都应调用同一套 `core/` 逻辑。DoubaoProvider 只是当前的一个模型实现，不代表项目绑定某一家平台。

## 安装

当前开发环境为 Windows + Python 3.14。请在项目根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## 配置 Doubao Vision（可选）

不使用真实视觉模型时，仍可使用文件预览、EasyOCR 和 Mock 测试流程。

若要使用 Doubao Vision：

1. 复制 `.env.example` 为 `.env`。
2. 在 `.env` 中填写自己的 Ark API Key 和模型 ID。
3. 不要提交 `.env`，不要在代码、截图或 Issue 中公开密钥。

```powershell
Copy-Item .env.example .env
```

`.env` 示例：

```text
ARK_API_KEY=<YOUR_ARK_API_KEY>
ARK_MODEL=<YOUR_ARK_MODEL_ID>
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

真实 API 调用可能产生费用，请先阅读对应平台的价格和权限说明。

## 运行

```powershell
.\.venv\Scripts\python -m streamlit run app.py
```

浏览器打开：<http://localhost:8501>

## 示例使用流程

1. 打开左侧菜单的“OCR 识别”。
2. 上传一张 PNG、JPG 或 JPEG 实验记录图片。
3. 点击“开始 AI 科研数据整理”。
4. 检查整理表格和黄色标记的不确定单元格。
5. 对每项选择采用 AI 建议、保留原始识别，或手动输入最终值。
6. 确认后生成并下载 Excel。

对于已经验证的 80 样品横向四栏图片，可在“高级设置（测试）”中手动启用“大图四栏预处理”。该功能仍处于实验阶段，默认关闭。

## 测试

项目保留了不依赖真实 API 的最小测试。例如：

```powershell
.\.venv\Scripts\python -m py_compile core\*.py providers\*.py prompts\*.py
```

真实图片、调试裁剪图和本地 API 配置不属于开源仓库内容。

## 当前限制

- 手写实验记录、模糊图片和密集横向多栏记录仍可能识别错误。
- OCR 或视觉模型输出必须由用户人工检查，尤其是样品编号、数字、小数点、正负号、单位和特殊符号。
- 大图四栏预处理目前只适用于已经验证尺寸与布局的实验记录图片。
- 尚未实现账户系统、数据库、云端部署、支付、自动统计分析或多模型自动路由。
- 当前不保证可直接发布为任何第三方 AI 平台的公开技能；未来应按平台正式能力提供适配层。

## 依赖

主要依赖包括 Streamlit、pandas、openpyxl、python-docx、EasyOCR、OpenAI Python SDK 和 python-dotenv。完整列表见 [requirements.txt](requirements.txt)。使用或发布前，请根据锁定版本再次核对第三方许可证与兼容性。

## 隐私与数据安全

- 本地上传文件只在当前运行期间处理，不写入项目目录。
- 使用 Doubao Vision 时，图片会发送到你配置的模型服务，请自行确认该服务的隐私政策和数据处理条款。
- 不要将真实实验数据、未脱敏图片、`.env` 或 API Key 提交到 GitHub。

## 许可证

本项目采用 [MIT License](LICENSE)。
