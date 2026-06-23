"""
历史片盘口抓取入口（薄入口）。

专门抓【已结算历史片】的全门槛历史 K 线 + 结算元数据，存进
data/historical_candlesticks/{片}.json，供 edge 回测用。

和 fetch_historical 的区别：
  - fetch_historical：抓 RT 评论 → historical/
  - fetch_candlesticks：抓 Kalshi 历史盘口 + 结算结果 → historical_candlesticks/
  两者分开跑（数据源不同、失败点不同）。

流程：
  1. 用 kalshi_event 调 events 接口，拿全部门槛 + final_score + settle_date + 各门槛result
  2. 时间范围：open_date(开盘) → close_date(结算)，把整个生命周期盘口都拉下来
     （回测时再按 RT 解禁日切片，数据宁可多存）
  3. 对每个门槛拉 candlesticks
  4. 全部组装存进一个 json（自包含：答案 + 所有门槛K线）

用法：py -m scripts.fetch_candlesticks --movie primate
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from src import config
from src.collectors.kalshi_client import (
    fetch_event_markets, fetch_candlesticks, iso_to_ts,
)

# 历史盘口存档目录
HIST_CANDLES_DIR = os.path.join("data", "historical_candlesticks")


def main():
    ap = argparse.ArgumentParser(description="抓历史片全门槛盘口 K 线（回测用）")
    ap.add_argument("--movie", required=True, help="config.WATCHLIST 里的 key")
    ap.add_argument("--interval", type=int, default=60,
                    help="K线粒度（分钟），默认 60")
    args = ap.parse_args()

    if args.movie not in config.WATCHLIST:
        raise SystemExit(f"未知电影 '{args.movie}'。请先加到 config.WATCHLIST。")
    m = config.WATCHLIST[args.movie]

    if "kalshi_event" not in m:
        raise SystemExit(f"'{args.movie}' 没填 kalshi_event，无法抓盘口。")
    event = m["kalshi_event"]

    # 1) 拿全部门槛 + 结算元数据
    print(f"🚀 拉取 {m['title']} 的门槛信息（event={event}）...")
    meta = fetch_event_markets(event)
    markets = meta["markets"]
    print(f"   找到 {len(markets)} 个门槛，官方最终分 {meta['final_score']}，"
          f"结算 {meta['settle_date']}")

    # 2) 时间范围：start 用真实开盘日(open_date)，end 用结算日。
    #    把整个市场生命周期的盘口都拉下来存档（回测时再按 RT 解禁日切）。
    end_ts = iso_to_ts(meta["settle_date"])
    if meta.get("open_date"):
        start_ts = iso_to_ts(meta["open_date"])
    else:
        # 兜底：万一某片没返回 open_date，退回结算前 35 天
        start_ts = end_ts - 35 * 24 * 3600
        print("   ⚠ 没拿到 open_date，用结算前 35 天兜底")
    print(f"   开盘 {meta.get('open_date')} → 结算 {meta['settle_date']}")
    print(f"   时间范围 Unix: {start_ts} → {end_ts}")

    # 3) 逐门槛拉 K 线
    out_markets = []
    for mk in markets:
        try:
            candles = fetch_candlesticks(
                event, mk["market_id"], start_ts, end_ts, args.interval
            )
            out_markets.append({**mk, "candles": candles})
            print(f"   门槛 {mk['floor']:.0f}: {len(candles)} 根 K 线")
        except Exception as e:
            print(f"   ⚠ 门槛 {mk['floor']:.0f} 拉取失败: {e}")
            out_markets.append({**mk, "candles": []})

    # 4) 组装存档（自包含：元数据 + 所有门槛K线）
    archive = {
        "event_ticker": event,
        "movie_key": args.movie,
        "final_score": meta["final_score"],
        "settle_date": meta["settle_date"],
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "interval_minutes": args.interval,
        "markets": out_markets,
    }

    os.makedirs(HIST_CANDLES_DIR, exist_ok=True)
    path = os.path.join(HIST_CANDLES_DIR, f"{args.movie}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=4)

    total = sum(len(x["candles"]) for x in out_markets)
    print(f"\n💾 已存档 {len(out_markets)} 个门槛、共 {total} 根 K 线到: {path}")


if __name__ == "__main__":
    main()