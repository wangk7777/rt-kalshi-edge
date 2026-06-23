"""
批量抓取历史片入口：一键把 watchlist 里所有【已结算】电影的
评论(historical/) + 盘口K线(historical_candlesticks/) 抓全，供回测用。

智能跳过：已经抓过的（存档文件已存在）自动跳过，只抓还没抓的新片。
所以你加了几十部新片后，跑一次就只抓新的；以后加片再跑，自动增量。

判断"该不该抓这部片"：
  - 必须是【已结算】片（有 kalshi_settle_date 且日期在今天之前）。
    进行中的片（没结算）走日常 fetch_reviews，不归这里管。
  - 评论/盘口存档已存在就跳过（除非 --force 强制重抓）。

错误隔离：某部片失败不影响其它片，最后汇总报告哪些成功/跳过/失败。

用法：
    py -m scripts.fetch_all_historical            # 只抓还没抓过的
    py -m scripts.fetch_all_historical --force    # 强制全部重抓
    py -m scripts.fetch_all_historical --movie primate   # 只抓某一部
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import time
from datetime import date, datetime

from src import config
from src.collectors.rt_reviews import fetch_reviews, save_reviews_historical
from src.collectors.kalshi_client import (
    fetch_event_markets, fetch_candlesticks, iso_to_ts,
)

HISTORICAL_DIR = os.path.join("data", "historical")
HIST_CANDLES_DIR = os.path.join("data", "historical_candlesticks")

# 每部片之间的礼貌延迟（秒），别把 RT / Kalshi 惹毛限速
DELAY_BETWEEN_MOVIES = 3


def is_settled(m: dict) -> bool:
    """判断是不是已结算历史片：有 kalshi_settle_date 且日期在今天之前。"""
    sd = m.get("kalshi_settle_date", "")
    if not sd:
        return False
    try:
        settle = date.fromisoformat(str(sd)[:10])   # 取前10位 YYYY-MM-DD
    except ValueError:
        return False
    return settle < date.today()


def reviews_archived(movie_key: str) -> bool:
    """评论存档已存在？historical/{片}_fullpull_*.json 有任意一个就算。"""
    pattern = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull_*.json")
    return len(glob.glob(pattern)) > 0


def candles_archived(movie_key: str) -> bool:
    """盘口存档已存在？historical_candlesticks/{片}.json 存在就算。"""
    return os.path.exists(os.path.join(HIST_CANDLES_DIR, f"{movie_key}.json"))


def grab_reviews(movie_key: str, m: dict) -> str:
    """抓评论存 historical/，返回路径。"""
    reviews = fetch_reviews(m["rt_movie_id"])
    path = save_reviews_historical(movie_key, reviews)
    return f"{len(reviews)} 条评论 → {path}"


def grab_candles(movie_key: str, m: dict, interval: int = 60) -> str:
    """抓全门槛盘口K线 + 结算元数据，存 historical_candlesticks/，返回摘要。"""
    event = m["kalshi_event"]
    meta = fetch_event_markets(event)

    end_ts = iso_to_ts(meta["settle_date"])
    if meta.get("open_date"):
        start_ts = iso_to_ts(meta["open_date"])
    else:
        start_ts = end_ts - 35 * 24 * 3600   # 兜底：结算前35天

    out_markets = []
    for mk in meta["markets"]:
        try:
            candles = fetch_candlesticks(
                event, mk["market_id"], start_ts, end_ts, interval
            )
            out_markets.append({**mk, "candles": candles})
        except Exception as e:
            out_markets.append({**mk, "candles": []})
            print(f"      ⚠ 门槛 {mk['floor']:.0f} 盘口拉取失败: {e}")

    archive = {
        "event_ticker": event,
        "movie_key": movie_key,
        "final_score": meta["final_score"],
        "settle_date": meta["settle_date"],
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "interval_minutes": interval,
        "markets": out_markets,
    }
    os.makedirs(HIST_CANDLES_DIR, exist_ok=True)
    path = os.path.join(HIST_CANDLES_DIR, f"{movie_key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=4)

    total = sum(len(x["candles"]) for x in out_markets)
    return f"{len(out_markets)} 门槛 / {total} 根K线 → {path}"


def main():
    ap = argparse.ArgumentParser(description="批量抓历史片评论+盘口（回测用）")
    ap.add_argument("--force", action="store_true", help="强制重抓（忽略已存档）")
    ap.add_argument("--movie", default=None, help="只抓某一部（key）")
    ap.add_argument("--interval", type=int, default=60, help="K线粒度分钟，默认60")
    args = ap.parse_args()

    # 决定要处理哪些片
    if args.movie:
        if args.movie not in config.WATCHLIST:
            raise SystemExit(f"未知电影 '{args.movie}'。")
        items = [(args.movie, config.WATCHLIST[args.movie])]
    else:
        items = list(config.WATCHLIST.items())

    # 统计
    done, skipped, failed = [], [], []

    # 先筛出"已结算"的历史片
    targets = [(k, m) for k, m in items if is_settled(m)]
    not_settled = [k for k, m in items if not is_settled(m)]

    print(f"📋 watchlist 共 {len(items)} 部，其中已结算历史片 {len(targets)} 部"
          f"（进行中/无结算日的 {len(not_settled)} 部跳过）\n")

    for i, (movie_key, m) in enumerate(targets, 1):
        title = m.get("title", movie_key)
        print(f"[{i}/{len(targets)}] {title} ({movie_key})")

        # 缺关键字段直接跳
        if "rt_movie_id" not in m or "kalshi_event" not in m:
            print(f"   ⚠ 缺 rt_movie_id 或 kalshi_event，跳过")
            failed.append(movie_key)
            continue

        try:
            # --- 评论 ---
            if reviews_archived(movie_key) and not args.force:
                print(f"   评论：已存档，跳过")
            else:
                print(f"   评论：抓取中...")
                print(f"      {grab_reviews(movie_key, m)}")

            # --- 盘口 ---
            if candles_archived(movie_key) and not args.force:
                print(f"   盘口：已存档，跳过")
            else:
                print(f"   盘口：抓取中...")
                print(f"      {grab_candles(movie_key, m, args.interval)}")

            done.append(movie_key)

        except Exception as e:
            print(f"   ❌ 失败: {e}")
            failed.append(movie_key)

        time.sleep(DELAY_BETWEEN_MOVIES)   # 礼貌延迟
        print()

    # 汇总
    print("=" * 50)
    print(f"✅ 完成 {len(done)} 部")
    if failed:
        print(f"❌ 失败 {len(failed)} 部: {', '.join(failed)}")
        print(f"   （可单独重跑：py -m scripts.fetch_all_historical --movie <key>）")
    if not_settled:
        print(f"⏭  跳过 {len(not_settled)} 部进行中/无结算日的片")


if __name__ == "__main__":
    main()