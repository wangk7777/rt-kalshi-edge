"""
历史片评论抓取入口（薄入口）。

专门抓【已结算的历史片】，存进 data/historical/，用于回测校准。
和 fetch_reviews 的区别：
  - fetch_reviews：抓正在进行的片，评论存 snapshots/ + 顺手抓盘口（金标准配对）
  - fetch_historical：抓历史片，只抓评论存 historical/，【不抓盘口】
    （历史片已结算，当前盘口要么拉不到、要么无意义；历史盘口早没了）

抓回来的是【当前全量】评论。回测时靠每条的 createDate 切片重建历史时点，
所以这里只管原原本本全量存档，不做切片。

用法：py -m scripts.archive_fetch.fetch_historical --movie zootopia_2
"""

from __future__ import annotations

import argparse

from src import config
from src.analysis.reviews import build_report, print_report
from src.collectors.rt_reviews import fetch_reviews, save_reviews_historical


def main():
    ap = argparse.ArgumentParser(description="抓历史片评论存 historical（回测用）")
    ap.add_argument("--movie", required=True, help="config.WATCHLIST 里的 key")
    args = ap.parse_args()

    if args.movie not in config.WATCHLIST:
        raise SystemExit(f"未知电影 '{args.movie}'。请先加到 config.WATCHLIST。")
    m = config.WATCHLIST[args.movie]

    if "rt_movie_id" not in m:
        raise SystemExit(
            f"'{args.movie}' 还没填 rt_movie_id。F12 找到 UUID 填进 config。"
        )

    print(f"🚀 抓取历史片 {m['title']} 的全量评论（存 historical）...\n")
    reviews = fetch_reviews(m["rt_movie_id"], movie_slug=args.movie)   # movie_key 即 URL slug

    path = save_reviews_historical(args.movie, reviews)
    print(f"\n💾 已存档 {len(reviews)} 条评论到: {path}")
    print("   （历史片不抓盘口）")

    # 顺手出一份质量报告，让你立刻判断这片数据干不干净、能不能用来回测
    print(f"\n📋 === {m['title']} 评论质量报告 ===")
    print_report(build_report(reviews))


if __name__ == "__main__":
    main()