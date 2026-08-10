# 可扩展 Benchmark 数据集

该目录只管理**可追溯清单、下载工具和质量检查工具**。二进制图片写入 `images/` 并被 Git 忽略，避免把大规模数据、许可证不明样本或用户图片提交到仓库。

## 首批公开样本

- 来源：[`nhop/SciGen-Figure`](https://huggingface.co/datasets/nhop/SciGen-Figure)
- 声明许可证：Apache-2.0
- 类型：科学论文中的已渲染表格图片（`printed_table`）
- 数量目标：100 张

这些样本用于验证科学表格、数值和多列表结构；**不等同于真实手写实验记录**。手写科研记录应只在明确可再分发、无个人敏感信息并完成许可证核验后加入。

`source_catalog.json` 记录了后续手写田野笔记、手写表格和科学表格候选来源。只有 `active_download_source` 可由脚本自动下载；其余来源必须先逐项核验许可证。

## 建立与下载

```powershell
# 仅生成 100 条可追溯 Manifest，不下载图片
.\.venv\Scripts\python tests\benchmark\datasets\collect_hf_scigen.py --limit 100

# 明确下载首批 100 张（不会调用 Doubao）
.\.venv\Scripts\python tests\benchmark\datasets\collect_hf_scigen.py --limit 100 --download

# 离线验证图片质量并生成报告
.\.venv\Scripts\python tests\benchmark\datasets\inspect_dataset.py
```

## 分阶段真实 API 测试

```powershell
# 建议先抽样 10 张
.\.venv\Scripts\python tests\benchmark\run_benchmark.py `
  --manifest tests\benchmark\datasets\images_manifest.json --limit 10 `
  --provider doubao --validation-provider doubao
```

逐步扩大到 50、100 张。没有人工真值时，Benchmark 只能报告行数和异常信号，不能判定“漏行”。

## 未来来源候选

- USGS Public Domain Field Notebook：适合 field notebook/手写观察样本，需按单张媒体页下载并保留来源。
- Smithsonian Open Access Field Books：适合自然科学田野记录；下载前确认具体 asset 的公开领域或 CC 标记。
- ScriptNet Handwritten Table：适合手写表格结构；先核验原始分发条款，再批量导入。

不要抓取个人社交平台、未授权实验室照片、含可识别个人或敏感实验信息的材料。
