"""从声明 Apache-2.0 的 SciGen-Figure 建立可重复的首批科学表格图片清单。

默认只生成 Manifest；传入 --download 才下载图片。该脚本不会调用项目 AI Provider。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


DATASET_ID = "nhop/SciGen-Figure"
CONFIG = "cl-test"
SPLIT = "test"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
ROWS_URL = "https://datasets-server.huggingface.co/rows?dataset={dataset}&config={config}&split={split}&offset={offset}&length={length}"
LICENSE = "Apache-2.0 (dataset card declaration; review underlying paper-image reuse before redistribution)"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = Path(__file__).parent


def fetch_json(url: str, attempts: int = 3) -> dict:
    """小范围重试公开数据集网络请求，避免单次传输中断破坏清单构建。"""
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "AI-Scientific-Data-Assistant-Benchmark/0.1"})
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except (IncompleteRead, OSError, URLError, json.JSONDecodeError) as error:
            if attempt == attempts:
                raise RuntimeError(f"公开数据集请求失败（已重试 {attempts} 次）：{error}") from error
            time.sleep(attempt)
    raise AssertionError("unreachable")


def fetch_rows(limit: int) -> list[dict]:
    rows: list[dict] = []
    batch_size = 25
    for offset in range(0, limit, batch_size):
        length = min(batch_size, limit - offset)
        url = ROWS_URL.format(
            dataset=DATASET_ID.replace("/", "%2F"),
            config=CONFIG,
            split=SPLIT,
            offset=offset,
            length=length,
        )
        rows.extend(fetch_json(url).get("rows", []))
    return rows


def build_entry(row: dict) -> dict:
    row_index = row["row_idx"]
    values = row["row"]
    relative_path = Path("tests") / "benchmark" / "datasets" / "images" / "scigen_figure" / CONFIG / f"{row_index:05d}.jpg"
    return {
        "image_path": relative_path.as_posix(),
        "source_url": f"{DATASET_URL}?config={CONFIG}&split={SPLIT}&row={row_index}",
        "source_type": "huggingface_dataset",
        "license": LICENSE,
        "category": "printed_table",
        "notes": f"SciGen-Figure row {row_index}; arXiv={values.get('arxiv_id', 'unknown')}; title={values.get('title', 'unknown')}",
        "dataset_id": DATASET_ID,
        "config": CONFIG,
        "split": SPLIT,
        "row_index": row_index,
        "expected_row_count": None,
    }


def download_image(url: str, destination: Path, attempts: int = 3) -> None:
    """下载到临时文件后再替换，避免网络中断留下截断图片。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "AI-Scientific-Data-Assistant-Benchmark/0.1"})
            with urlopen(request, timeout=120) as response:
                data = response.read()
            temporary.write_bytes(data)
            temporary.replace(destination)
            return
        except (IncompleteRead, OSError, URLError) as error:
            temporary.unlink(missing_ok=True)
            if attempt == attempts:
                raise RuntimeError(f"图片下载失败（已重试 {attempts} 次）：{destination.name}: {error}") from error
            time.sleep(attempt)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成或下载 SciGen-Figure 基准样本")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--download", action="store_true", help="显式下载图片；默认仅写 Manifest")
    parser.add_argument("--manifest", default=str(DATASET_DIR / "images_manifest.json"))
    arguments = parser.parse_args()

    rows = fetch_rows(arguments.limit)
    if len(rows) < arguments.limit:
        raise RuntimeError(f"来源仅返回 {len(rows)} 行，少于请求的 {arguments.limit} 行。")
    entries = [build_entry(row) for row in rows]
    manifest = {
        "schema_version": 1,
        "generated_by": "collect_hf_scigen.py",
        "images": entries,
    }
    manifest_path = Path(arguments.manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    downloaded = 0
    failures: list[dict[str, str]] = []
    if arguments.download:
        for row, entry in zip(rows, entries):
            image_url = row["row"]["figure"]["src"]
            destination = PROJECT_ROOT / entry["image_path"]
            if destination.is_file():
                downloaded += 1
                continue
            try:
                download_image(image_url, destination)
                downloaded += 1
            except RuntimeError as error:
                failures.append({"image_path": entry["image_path"], "error": str(error)})
    print(json.dumps({
        "manifest": str(manifest_path),
        "entries": len(entries),
        "downloaded": downloaded,
        "failed_downloads": failures,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
