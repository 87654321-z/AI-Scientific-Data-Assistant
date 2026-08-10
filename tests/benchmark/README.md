# 真实图片基准测试

这个目录提供一个独立的命令行基准工具。它复用当前项目已有的：

`图片 → Extraction → Validation → Review 就绪统计 → Excel 导出检查`

工具不会修改 Prompt、Provider、核心业务逻辑或 Streamlit 页面。

## 小规模离线验证

默认使用 Mock Provider，不会调用外部 API：

```powershell
.\.venv\Scripts\python tests\benchmark\run_benchmark.py `
  test_images\微信图片_20260726111931_2_2.jpg
```

## 真实 API 基准测试

只有显式指定 `doubao` 才会调用真实 API，并使用当前 `.env` 或网页配置之外的本地运行配置：

```powershell
.\.venv\Scripts\python tests\benchmark\run_benchmark.py `
  test_images\图片1.jpg test_images\图片2.jpg `
  --provider doubao --validation-provider doubao
```

也可以把每行一个图片路径写入文本文件：

```powershell
.\.venv\Scripts\python tests\benchmark\run_benchmark.py `
  --images-file tests\benchmark\images.txt `
  --provider doubao --validation-provider doubao
```

## 大规模运行与资源释放

默认每批处理 10 张。每批结束后会清理 Python 临时对象并执行垃圾回收；Excel 检查使用系统临时目录，完成后自动释放。

```powershell
.\.venv\Scripts\python tests\benchmark\run_benchmark.py `
  --manifest tests\benchmark\datasets\images_manifest.json --limit 10 `
  --batch-size 10 --provider doubao --validation-provider doubao
```

默认会在运行结束后删除本次处理的 `tests/benchmark/datasets/images/` 托管下载图片及 `.part` 临时文件，但不会删除 `test_images/` 或其他手工传入的图片。报告 JSON/Markdown 与 Manifest 始终保留。

只有需要复用下载图片时才加 `--keep-files`：

```powershell
.\.venv\Scripts\python tests\benchmark\run_benchmark.py `
  --manifest tests\benchmark\datasets\images_manifest.json --limit 10 `
  --batch-size 10 --keep-files
```

## 报告内容

每张图片都会记录：

- Extraction 是否成功、耗时、行数和字段名；
- 疑似视觉布局字段；
- treatment_id/sample_id 是否被拆分；
- 编号中 `/`、`+`、`-` 的疑似异常；
- 数值字段中的字母异常；
- 重复实验是否被压缩为数组、列表或逗号字符串；
- Validation 的 warnings、suggestions、uncertain_items 数量；
- 可进入 Review 的单元格数量；
- Excel 是否可生成以及是否含三个工作表。

同时会生成汇总指标：总图片数、Extraction/Validation/Excel 成功率、平均 Extraction 耗时、平均行数、字段异常次数、编号字符异常次数、数值字母异常次数、重复值压缩次数和 Review 可确认总数。

默认报告写入 `tests/benchmark/results/`，该目录已被本目录的 `.gitignore` 忽略。公开样本加入前，请确认图片许可证允许下载、保存和测试，并在图片清单中保留来源链接与许可证说明。
