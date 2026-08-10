"""离线检查基准数据集图片质量并生成 Markdown 报告。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = Path(__file__).parent


def load_entries(manifest_path: Path) -> list[dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return data.get("images", data) if isinstance(data, dict) else data


def inspect_entries(entries: list[dict]) -> dict:
    categories = Counter(entry.get("category", "unknown") for entry in entries)
    sources = Counter(entry.get("source_type", "unknown") for entry in entries)
    licenses = Counter(entry.get("license", "unknown") for entry in entries)
    downloaded = 0
    corrupt: list[str] = []
    too_small: list[str] = []
    dimensions: list[tuple[int, int]] = []

    for entry in entries:
        path = PROJECT_ROOT / entry["image_path"]
        if not path.is_file():
            continue
        downloaded += 1
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
            dimensions.append((width, height))
            if min(width, height) < 100:
                too_small.append(entry["image_path"])
        except Exception:
            corrupt.append(entry["image_path"])

    return {
        "manifest_entries": len(entries),
        "downloaded_images": downloaded,
        "missing_images": len(entries) - downloaded,
        "categories": dict(sorted(categories.items())),
        "source_types": dict(sorted(sources.items())),
        "licenses": dict(sorted(licenses.items())),
        "corrupt_images": corrupt,
        "too_small_images": too_small,
        "min_dimensions": list(map(min, zip(*dimensions))) if dimensions else None,
        "max_dimensions": list(map(max, zip(*dimensions))) if dimensions else None,
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# Benchmark 数据集报告",
        "",
        f"- Manifest 图片数：{summary['manifest_entries']}",
        f"- 已下载并可检查图片数：{summary['downloaded_images']}",
        f"- 尚未下载图片数：{summary['missing_images']}",
        f"- 损坏图片数：{len(summary['corrupt_images'])}",
        f"- 过小图片数：{len(summary['too_small_images'])}",
        "",
        "## 分类统计",
        "",
    ]
    lines.extend(f"- {category}: {count}" for category, count in summary["categories"].items())
    lines.extend([
        "",
        "## 后续测试建议",
        "",
        "1. 先用 `--manifest ... --limit 10 --provider doubao --validation-provider doubao` 做费用受控抽样。",
        "2. 通过人工标注 `expected_row_count` 后再统计漏行；无真值时只报告行数，不能声称发现漏行。",
        "3. 补充可再分发的手写科研记录前，先核验单张图片或数据集的许可证与隐私条件。",
        "4. 逐步扩大抽样规模：10 → 50 → 100；不要直接对全部样本调用 API。",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 Benchmark 数据集图片质量")
    parser.add_argument("--manifest", default=str(DATASET_DIR / "images_manifest.json"))
    parser.add_argument("--report", default=str(DATASET_DIR / "benchmark_dataset_report.md"))
    arguments = parser.parse_args()
    summary = inspect_entries(load_entries(Path(arguments.manifest)))
    Path(arguments.report).write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
