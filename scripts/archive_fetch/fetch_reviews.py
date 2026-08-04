"""
抓当前开盘电影的rt评论的命令入口（薄入口：只负责串联，真正干活的能力在 src/ 里）。

它做三件事：解析命令行 → 调 collectors 抓评论和orderbook并存档 → 调 analysis 体检并打印。

用法（在项目根目录运行）：
    py -m scripts.archive_fetch.fetch_reviews --movie toy_story_5

电影专属的 RT UUID 存在 config.WATCHLIST 的 rt_movie_id 字段里
（每部片去烂番茄网页 F12 → 网络 → Fetch/XHR → 搜 reviews 找到）。

设计：抓取和跑模型是【两个独立步骤】，故意不合并。
原因：评论几小时才变一次，没必要每次跑模型都重抓（慢、对服务器不友好）；
而且抓取/拉价各有各的失败点，分开跑出错好定位。
"""

from __future__ import annotations

import argparse

from src import config
from src.analysis.reviews import build_report, print_report
from src.collectors.rt_reviews import fetch_reviews, save_reviews


def main():
    ap = argparse.ArgumentParser(description="抓取烂番茄评论并体检")
    ap.add_argument("--movie", required=True, help="config.WATCHLIST 里的 key")
    args = ap.parse_args()

    if args.movie not in config.WATCHLIST:
        raise SystemExit(f"未知电影 '{args.movie}'。请先加到 config.WATCHLIST。")
    m = config.WATCHLIST[args.movie]

    if "rt_movie_id" not in m:
        raise SystemExit(
            f"'{args.movie}' 还没填 rt_movie_id。"
            f"去烂番茄网页 F12 找到这部片的 UUID，填进 config。"
        )

    print(f"🚀 开始抓取 {m['title']} 的评论...\n")
    reviews = fetch_reviews(m["rt_movie_id"])

    # 存档评论
    path = save_reviews(args.movie, reviews)
    print(f"\n💾 已存档 {len(reviews)} 条评论到: {path}")

    # 报告
    print(f"\n📋 === {m['title']} 评论质量报告 ===")
    report = build_report(reviews)
    print_report(report)

    # 打印下一步命令（自动填好 score 和 reviews）
    score = report["tomatometer"]
    n = report["n_total"]
    print(f"\n💡 下一步（复制运行，加 --live 拉实时价）：")
    print(f"py -m scripts.run_analysis --movie {args.movie} "
          f"--score {score:.1f} --reviews {n} --live")


if __name__ == "__main__":
    main()