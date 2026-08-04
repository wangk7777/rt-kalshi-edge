"""
重看报告入口（薄入口）：读一个已存的评论 JSON，重新出质量报告。

不抓取、不联网，纯读本地文件。snapshots/ 和 historical/ 的 JSON 都能读
（它们格式一样，都是评论列表）。

用法：
    py -m scripts.archive_old.show_report data/snapshots/toy_story_5/2026-06-21.json
    py -m scripts.archive_old.show_report data/historical/zootopia_2_fullpull_2026-06-22.json
"""

from __future__ import annotations

import argparse
import json

from src.analysis.reviews import build_report, print_report


def main():
    ap = argparse.ArgumentParser(description="读已存 JSON 重新出报告")
    ap.add_argument("path", help="评论 JSON 文件路径")
    args = ap.parse_args()

    try:
        with open(args.path, encoding="utf-8") as f:
            reviews = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"找不到文件: {args.path}")
    except json.JSONDecodeError:
        raise SystemExit(f"文件不是合法 JSON: {args.path}")

    print(f"📋 === 报告 (来自 {args.path}) ===")
    print_report(build_report(reviews))


if __name__ == "__main__":
    main()