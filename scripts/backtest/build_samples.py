"""
回测提炼脚本：把历史片的评论 + 盘口，提炼成一张干净的样本表 samples.csv。

每一行 = 一个"决策时点 × 一个门槛"的客观事实快照，包含：
  - 当时的评论状态（score, n）—— createDate 切片算的
  - 当时的市场价（yes_ask/yes_bid）—— candlestick 里决策时刻前最近的一根
  - 流动性指标（价差、成交量）—— 判断这个市场价可不可信
  - 最终结算结果（result, final_score）—— 回测的标准答案

注意：这张表【只含客观事实，不含任何模型参数】。
公平价、edge 留到回测本体里算（那时才代入不同 drift/prior 扫参数）。
这样 samples.csv 是个不依赖参数的"事实表"，可反复用于不同回测实验。

用法：py -m scripts.backtest.build_samples
输出：data/backtest/samples.csv
"""

from __future__ import annotations

import csv
import glob
import json
import os
from datetime import datetime, timezone, timedelta

from src import config

HISTORICAL_DIR = os.path.join("data", "historical")
HIST_CANDLES_DIR = os.path.join("data", "historical_candlesticks")
OUT_DIR = os.path.join("data", "backtest")

# 决策时点：解禁后第几天
DECISION_DAYS = [0, 1, 2, 3, 4, 5]
# 取市场价时，决策时刻前最多往回找多少小时（超过说明那时没数据）
MAX_PRICE_GAP_HOURS = 48


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def is_fresh(r):
    s = str(r.get("sentiment", ""))
    return "Fresh" in s or s.upper() == "POSITIVE"


def load_reviews(movie_key):
    # 读固定文件名的历史评论存档
    path = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def load_candles(movie_key):
    path = os.path.join(HIST_CANDLES_DIR, f"{movie_key}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def slice_at(reviews, cutoff_dt):
    """createDate <= cutoff 的评论的新鲜度和条数。"""
    valid = [r for r in reviews
             if parse_dt(r.get("date")) and parse_dt(r["date"]) <= cutoff_dt]
    if not valid:
        return None, 0
    fresh = sum(1 for r in valid if is_fresh(r))
    return round(fresh / len(valid) * 100), len(valid)


def price_at(candles, target_dt, max_gap_hours=MAX_PRICE_GAP_HOURS):
    """
    取决策时刻的市场价：candles 里 ts <= target 的、最近的那根。
    不能用未来的价格（那是作弊）。太远（超 max_gap）说明当时没数据，返回 None。
    """
    target_ts = int(target_dt.timestamp())
    past = [c for c in candles if c.get("ts") is not None and c["ts"] <= target_ts]
    if not past:
        return None
    closest = max(past, key=lambda c: c["ts"])
    if (target_ts - closest["ts"]) / 3600 > max_gap_hours:
        return None
    return closest


def main():
    from datetime import date

    def is_settled(m):
        sd = m.get("kalshi_settle_date", "")
        try:
            return bool(sd) and date.fromisoformat(str(sd)[:10]) < date.today()
        except ValueError:
            return False

    movies = [(k, m) for k, m in config.WATCHLIST.items()
              if is_settled(m) and not m.get("exclude_from_backtest", False)]
    excluded = [k for k, m in config.WATCHLIST.items()
                if is_settled(m) and m.get("exclude_from_backtest", False)]
    if excluded:
        print(f"排除 {len(excluded)} 部（exclude_from_backtest）: {', '.join(excluded)}\n")

    print(f"提炼 {len(movies)} 部已结算历史片...\n")

    rows = []
    stats = {"no_reviews": 0, "no_candles": 0, "done": 0}

    for movie_key, m in movies:
        reviews = load_reviews(movie_key)
        candles_data = load_candles(movie_key)

        if not reviews:
            stats["no_reviews"] += 1
            continue
        if not candles_data:
            stats["no_candles"] += 1
            continue

        dates = sorted([parse_dt(r.get("date")) for r in reviews if parse_dt(r.get("date"))])
        if not dates:
            continue

        # 解禁日选择（三级优先）：
        # 1. config 手填的 embargo_date 最高优先
        # 2. 若首日只有1条评论（孤儿污染）→ 用次日
        # 3. 否则用最早评论日
        embargo_str = m.get("embargo_date")
        if embargo_str:
            lift_date = parse_dt(embargo_str + "T00:00:00Z")
        else:
            earliest = dates[0]
            first_day = earliest.date()
            n_first_day = sum(1 for d in dates if d.date() == first_day)
            if n_first_day == 1:
                # 首日孤儿：解禁日 = 次日（第一条评论之后那天）
                next_day = first_day + timedelta(days=1)
                lift_date = parse_dt(next_day.isoformat() + "T00:00:00Z")
            else:
                lift_date = earliest
        # 归到当天零点（配合切当天23:59:59）
        lift_date = lift_date.replace(hour=0, minute=0, second=0, microsecond=0)

        markets = candles_data.get("markets", [])
        final_score = candles_data.get("final_score")
        base_rate = m.get("base_rate")

        # 对每个决策时点 × 每个门槛，生成一行
        for d in DECISION_DAYS:
            cutoff = lift_date + timedelta(days=d, hours=23, minutes=59, seconds=59)
            score, n = slice_at(reviews, cutoff)
            if score is None or n == 0:
                continue   # 那时还没评论，跳过

            for mk in markets:
                floor = mk.get("floor")
                result = mk.get("result")       # 'yes'/'no'
                mk_candles = mk.get("candles", [])
                if not mk_candles or floor is None:
                    continue

                c = price_at(mk_candles, cutoff)
                if c is None:
                    continue   # 决策时刻没有市场价数据

                yes_ask = c.get("yes_ask")
                yes_bid = c.get("yes_bid")
                volume = c.get("volume", 0)
                spread = (yes_ask - yes_bid) if (yes_ask is not None and yes_bid is not None) else None

                rows.append({
                    "movie_key": movie_key,
                    "decision_day": d,              # 解禁后第几天
                    "decision_date": cutoff.date().isoformat(),
                    "score_at_decision": score,     # 当时新鲜度%
                    "n_at_decision": n,             # 当时评论数
                    "base_rate": base_rate,         # 先验中心（回测算公平价要用）
                    "floor": floor,                 # 门槛
                    "yes_ask": yes_ask,             # 当时买YES价（算多头edge用）
                    "yes_bid": yes_bid,             # 当时卖YES价
                    "spread": spread,               # 价差（流动性）
                    "volume": volume,               # 成交量（流动性）
                    "final_score": final_score,     # 官方最终分（标准答案）
                    "result": result,               # 门槛结算 yes/no（标准答案）
                    "settle_date": m.get("kalshi_settle_date", ""),
                })

        stats["done"] += 1

    # 写出 CSV
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "samples.csv")
    if rows:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    # 汇总
    print(f"✅ 提炼完成")
    print(f"   处理电影: {stats['done']} 部")
    print(f"   跳过(无评论): {stats['no_reviews']} 部")
    print(f"   跳过(无盘口): {stats['no_candles']} 部")
    print(f"   生成样本: {len(rows)} 行 → {out_path}")

    # 流动性快速统计（帮你定第4点的阈值）
    if rows:
        with_vol = sum(1 for r in rows if r["volume"] and r["volume"] > 0)
        spreads = [r["spread"] for r in rows if r["spread"] is not None]
        print(f"\n   流动性概览（帮你定过滤阈值）:")
        print(f"     有成交量(vol>0)的样本: {with_vol}/{len(rows)} "
              f"({with_vol*100//len(rows)}%)")
        if spreads:
            spreads.sort()
            print(f"     价差中位数: {spreads[len(spreads)//2]}¢")
            print(f"     价差<=5¢的: {sum(1 for s in spreads if s<=5)} 个")
            print(f"     价差<=15¢的: {sum(1 for s in spreads if s<=15)} 个")
            print(f"     价差>50¢的(几乎不可交易): {sum(1 for s in spreads if s>50)} 个")


if __name__ == "__main__":
    main()