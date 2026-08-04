"""
PnL专用数据集：每部片 × 每根小时candle × 每门槛 = 一行。
用于模拟"每小时盯盘、按信息量(n)和胜率交易"的真实策略。

与 build_samples.py（校准回测用，每片每天一套门槛）的区别：
  - 这里每根小时candle都展开成样本（抓住盘口每小时波动）
  - 评论切片按candle的精确时间戳切（不是切到当天23:59）
  - 输出 samples_pnl.csv（旧的 samples.csv 保留给参数校准）

用法：py -m scripts.backtest.build_samples_pnl
输出：data/backtest/samples_pnl.csv
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


def parse_dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def is_fresh(r):
    s = str(r.get("sentiment", ""))
    return "Fresh" in s or s.upper() == "POSITIVE"


def load_reviews(movie_key):
    path = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def load_candles(movie_key):
    path = os.path.join(HIST_CANDLES_DIR, f"{movie_key}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def compute_lift_date(reviews, m):
    """解禁日：embargo_date > 首日1条取次日 > 最早评论日。归零点。"""
    dates = sorted([parse_dt(r.get("date")) for r in reviews if parse_dt(r.get("date"))])
    if not dates:
        return None
    embargo_str = m.get("embargo_date")
    if embargo_str:
        lift = parse_dt(embargo_str + "T00:00:00Z")
    else:
        earliest = dates[0]
        first_day = earliest.date()
        n_first = sum(1 for d in dates if d.date() == first_day)
        if n_first == 1:
            lift = parse_dt((first_day + timedelta(days=1)).isoformat() + "T00:00:00Z")
        else:
            lift = earliest
    return lift.replace(hour=0, minute=0, second=0, microsecond=0)


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
        print(f"排除 {len(excluded)} 部（exclude_from_backtest）\n")
    print(f"提炼 {len(movies)} 部历史片的每小时PnL数据集...\n")

    rows = []
    stats = {"done": 0, "no_reviews": 0, "no_candles": 0}

    for movie_key, m in movies:
        reviews = load_reviews(movie_key)
        candles_data = load_candles(movie_key)
        if not reviews:
            stats["no_reviews"] += 1
            continue
        if not candles_data:
            stats["no_candles"] += 1
            continue

        lift_date = compute_lift_date(reviews, m)
        if lift_date is None:
            continue

        # 评论按时间排序（双指针用）
        review_times = sorted(
            [(parse_dt(r.get("date")), is_fresh(r))
             for r in reviews if parse_dt(r.get("date"))],
            key=lambda x: x[0]
        )

        final_score = candles_data.get("final_score")
        base_rate = m.get("base_rate")
        settle_date = m.get("kalshi_settle_date", "")
        markets = candles_data.get("markets", [])

        for mk in markets:
            floor = mk.get("floor")
            result = mk.get("result")
            mk_candles = mk.get("candles", [])
            if floor is None or not mk_candles:
                continue

            # candle 按时间排序
            sorted_candles = sorted(
                [c for c in mk_candles if c.get("ts") is not None],
                key=lambda c: c["ts"]
            )

            # 双指针切片：对每根candle算 createDate<=candle时刻 的评论
            ptr = 0
            fresh = 0
            total = 0
            for c in sorted_candles:
                c_dt = datetime.fromtimestamp(c["ts"], tz=timezone.utc)
                # 只要解禁日及之后的candle（解禁前没评论、不交易）
                if c_dt < lift_date:
                    continue
                # 纳入所有 <= c_dt 的评论
                while ptr < len(review_times) and review_times[ptr][0] <= c_dt:
                    total += 1
                    if review_times[ptr][1]:
                        fresh += 1
                    ptr += 1
                if total == 0:
                    continue   # 那一刻还没评论
                score = round(fresh / total * 100)

                yes_ask = c.get("yes_ask")
                yes_bid = c.get("yes_bid")
                volume = c.get("volume", 0)
                spread = (yes_ask - yes_bid) if (yes_ask is not None and yes_bid is not None) else None
                hours_since = int((c_dt - lift_date).total_seconds() // 3600)

                rows.append({
                    "movie_key": movie_key,
                    "decision_time": c_dt.strftime("%Y-%m-%d %H:%M"),
                    "hours_since_embargo": hours_since,
                    "score_at_decision": score,
                    "n_at_decision": total,
                    "base_rate": base_rate,
                    "floor": floor,
                    "yes_ask": yes_ask,
                    "yes_bid": yes_bid,
                    "spread": spread,
                    "volume": volume,
                    "final_score": final_score,
                    "result": result,
                    "settle_date": settle_date,
                })

        stats["done"] += 1
        if stats["done"] % 20 == 0:
            print(f"  已处理 {stats['done']}/{len(movies)} 部，当前 {len(rows)} 行")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "samples_pnl.csv")
    if rows:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print(f"\n✅ 完成")
    print(f"   处理: {stats['done']} 部, 跳过无评论{stats['no_reviews']}/无盘口{stats['no_candles']}")
    print(f"   生成: {len(rows)} 行 → {out_path}")

    if rows:
        # 概览
        import statistics
        n_vals = [r["n_at_decision"] for r in rows]
        hours = [r["hours_since_embargo"] for r in rows]
        n40 = sum(1 for n in n_vals if n >= 40)
        print(f"\n   概览:")
        print(f"     n≥40的行(可交易候选): {n40}/{len(rows)} ({n40*100//len(rows)}%)")
        print(f"     解禁后小时数: 中位{int(statistics.median(hours))}, 最大{max(hours)}")
        spreads = [r["spread"] for r in rows if r["spread"] is not None]
        if spreads:
            spreads.sort()
            print(f"     价差中位: {spreads[len(spreads)//2]}¢, ≤10¢占{sum(1 for s in spreads if s<=10)*100//len(spreads)}%")


if __name__ == "__main__":
    main()