"""
回测前数据体检：遍历所有历史片，检查评论 + 盘口数据的完整性和质量。
在回测前跑一次，把脏数据揪出来，别让数据问题伪装成模型结论。

用法：py -m scripts.archive_old.check_data_health
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime

from src import config

HISTORICAL_DIR = os.path.join("data", "historical")
HIST_CANDLES_DIR = os.path.join("data", "historical_candlesticks")


def parse_date(s):
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
    # 优先读固定名的新文件
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


def tomatometer_at(reviews, cutoff):
    """算 createDate <= cutoff 的评论的新鲜度。"""
    valid = [r for r in reviews
             if parse_date(r.get("date")) and parse_date(r["date"]) <= cutoff]
    if not valid:
        return None, 0
    fresh = sum(1 for r in valid if is_fresh(r))
    return fresh / len(valid) * 100, len(valid)


def main():
    problems = []   # 收集所有问题
    ok_count = 0

    # 只体检已结算历史片
    from datetime import date
    def is_settled(m):
        sd = m.get("kalshi_settle_date", "")
        if not sd:
            return False
        try:
            return date.fromisoformat(str(sd)[:10]) < date.today()
        except ValueError:
            return False

    movies = [(k, m) for k, m in config.WATCHLIST.items() if is_settled(m)]
    print(f"体检 {len(movies)} 部已结算历史片...\n")

    for movie_key, m in movies:
        issues = []   # 这部片的问题

        # --- 评论检查 ---
        reviews = load_reviews(movie_key)
        if reviews is None:
            issues.append("❌ 无评论存档")
        else:
            n = len(reviews)
            no_date = sum(1 for r in reviews if not r.get("date"))
            if n < 20:
                issues.append(f"⚠ 评论太少({n}条)")
            if no_date > 0:
                issues.append(f"⚠ {no_date}条评论缺date(影响切片)")

        # --- 盘口检查 ---
        candles = load_candles(movie_key)
        if candles is None:
            issues.append("❌ 无盘口存档")
        else:
            markets = candles.get("markets", [])
            total_m = len(markets)
            empty_m = sum(1 for mk in markets if not mk.get("candles"))
            traded_m = sum(1 for mk in markets
                           if any(c["volume"] > 0 for c in mk.get("candles", [])))
            if total_m == 0:
                issues.append("❌ 盘口无门槛")
            elif empty_m == total_m:
                issues.append("❌ 所有门槛盘口全空")
            elif traded_m == 0:
                issues.append("⚠ 所有门槛都无成交(冷门片,edge价值低)")

        # --- 交叉检查：切片最终分 vs 官方final_score ---
        if reviews and candles:
            settle = candles.get("settle_date")
            official = candles.get("final_score")
            cut = parse_date(settle)
            if cut and official is not None:
                sliced, sn = tomatometer_at(reviews, cut)
                if sliced is not None:
                    try:
                        diff = abs(sliced - float(official))
                        if diff > 8:
                            issues.append(
                                f"⚠ 切片分{sliced:.0f}% vs 官方{official}% 差{diff:.0f}点(偏大)")
                    except (ValueError, TypeError):
                        pass

        # --- config 检查：base_rate 还是占位的90吗 ---
        if m.get("base_rate") == 90:
            issues.append("⚠ base_rate还是占位90(未查真实值)")

        if issues:
            problems.append((movie_key, issues))
        else:
            ok_count += 1

    # --- 汇总报告 ---
    print(f"✅ 完全健康: {ok_count} 部\n")
    if problems:
        print(f"发现问题的片 {len(problems)} 部:\n")
        # 按严重程度：有❌的排前面
        problems.sort(key=lambda x: (not any("❌" in i for i in x[1]), x[0]))
        for movie_key, issues in problems:
            print(f"  {movie_key}:")
            for i in issues:
                print(f"      {i}")

    # 统计各类问题
    print("\n=== 问题类型统计 ===")
    all_issues = [i for _, issues in problems for i in issues]
    from collections import Counter
    cats = Counter()
    for i in all_issues:
        key = i.split("(")[0].strip()
        cats[key] += 1
    for cat, cnt in cats.most_common():
        print(f"  {cat}: {cnt} 部")


if __name__ == "__main__":
    main()