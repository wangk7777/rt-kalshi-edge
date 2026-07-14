"""
回测本体 v1：用固定参数(drift/prior)对全样本跑模型，
按 n 分层输出 Brier 分数和校准曲线，回答"模型概率准不准"。

v1 不扫参数、不分校准/验证组——先跑通、看第一个真实结果。
回测用【真实 n_final】（从评论文件切到结算日的条数），不用 config 的预估值。

用法：py -m scripts.backtest
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime
from collections import defaultdict

from src import config
from src.model.bayesian import ModelInputs, run_model

SAMPLES_PATH = os.path.join("data", "backtest", "samples.csv")
HISTORICAL_DIR = os.path.join("data", "historical")

# ==== 回测参数 ====
DRIFT = 2.0
PRIOR_STRENGTH = 10.0
N_SIMS = 200_000        # 蒙特卡洛次数（v1用足量；扫参数时再降）
SPREAD_MAX = 10         # 流动性过滤：价差>此值的样本算edge时不用（但概率校准仍用全部）

# n 分层边界
def n_layer_name(n):
    if n < 10: return "<10"
    if n < 20: return "10-20"
    if n < 40: return "20-40"
    if n < 80: return "40-80"
    return "80+"


def parse_dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_n_final(movie_key, settle_date_str):
    """真实 n_final = 评论文件里 createDate <= 结算日 的条数。"""
    path = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        reviews = json.load(f)
    settle = parse_dt(settle_date_str)
    if settle is None:
        return len(reviews)
    # Kalshi 结算在结算日 10:00 AM EDT = 14:00 UTC。
    # 切到这个时刻，才是 Kalshi 结算时真正算进去的评论数。
    if settle.tzinfo is None:
        from datetime import timezone, timedelta
        settle = settle.replace(tzinfo=timezone.utc) + timedelta(hours=14)
    count = sum(1 for r in reviews
                if parse_dt(r.get("date")) and parse_dt(r["date"]) <= settle)
    return count


def brier(pairs):
    if not pairs:
        return None
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs)


def print_calibration(pairs, n_bins=10):
    bins = [[] for _ in range(n_bins)]
    for p, a in pairs:
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, a))
    print("  校准曲线（预测概率 → 实际发生频率，理想情况两者相等）:")
    for i, b in enumerate(bins):
        if not b:
            continue
        avg_pred = sum(p for p, a in b) / len(b)
        actual = sum(a for p, a in b) / len(b)
        bar = "█" * int(actual * 30)
        print(f"    预测[{i/n_bins:.1f}-{(i+1)/n_bins:.1f}] "
              f"均值{avg_pred:.2f} → 实际{actual:.2f} (n={len(b):4}) {bar}")


def main():

    # ==== 运行开始时间 ====
    start_time = datetime.now()
    print(f"🕐 回测开始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 读样本
    with open(SAMPLES_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"读入 {len(rows)} 行样本（v1：全样本，不分校准/验证组）\n")
    print(f"参数: drift={DRIFT}, prior_strength={PRIOR_STRENGTH}, n_sims={N_SIMS}\n")

    # ==== v2 会用的校准/验证切分（v1 先不用，预留）====
    # 校准组: settle_date <= "2025-06-30"（2024 + 2025上半年，约67部）
    # 验证组: "2025-07-01" ~ "2025-12-31"（2025下半年）
    # 样本外: 2026 全年（最后模拟真实交易）
    # v2 扫参数时：在校准组找最优 drift/prior，验证组算 Brier。

    # 预先算真实 n_final
    n_final_cache = {}
    for r in rows:
        mk = r["movie_key"]
        if mk not in n_final_cache:
            n_final_cache[mk] = compute_n_final(mk, r["settle_date"])

    all_pairs = []
    layer_pairs = defaultdict(list)
    day_pairs = defaultdict(list)
    skipped = 0

    for i, r in enumerate(rows):
        n_now = int(r["n_at_decision"])
        score_now = float(r["score_at_decision"])
        base_rate = float(r["base_rate"])
        floor = float(r["floor"])
        result = r["result"]
        n_final = n_final_cache.get(r["movie_key"])

        if n_final is None or n_now == 0 or result not in ("yes", "no"):
            skipped += 1
            continue
        if n_final < n_now:
            n_final = n_now

        inp = ModelInputs(
            score_now=score_now, n_now=n_now, base_rate=base_rate,
            prior_strength=PRIOR_STRENGTH, n_final=n_final, drift=DRIFT,
        )
        res = run_model(inp, n_sims=N_SIMS)
        prob = res.prob_at_least(floor)
        actual = 1 if result == "yes" else 0

        all_pairs.append((prob, actual))
        layer_pairs[n_layer_name(n_now)].append((prob, actual))
        day_pairs[r["decision_day"]].append((prob, actual))

        if (i + 1) % 500 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"  已处理 {i+1}/{len(rows)}，耗时 {elapsed:.0f}秒")

    # ==== 结果汇总 ====
    overall_brier = brier(all_pairs)
    layer_results = {}
    for name in ["<10", "10-20", "20-40", "40-80", "80+"]:
        b = brier(layer_pairs[name])
        layer_results[name] = {"brier": b, "n_samples": len(layer_pairs[name])}
    day_results = {}
    for day in ["0", "3", "7", "14"]:
        b = brier(day_pairs[day])
        day_results[day] = {"brier": b, "n_samples": len(day_pairs[day])}

    # ==== 打印 ====
    print("\n" + "=" * 55)
    print(f"总体 Brier: {overall_brier:.4f}   (0.25=瞎猜, 越低越准)")
    print(f"样本数: {len(all_pairs)}，跳过 {skipped}")
    print("=" * 55)
    print_calibration(all_pairs)

    print("\n" + "=" * 55)
    print("按 n（决策时评论数）分层 —— 看评论多少才可靠")
    print("=" * 55)
    for name in ["<10", "10-20", "20-40", "40-80", "80+"]:
        lr = layer_results[name]
        bstr = f"{lr['brier']:.4f}" if lr['brier'] is not None else "无样本"
        print(f"  n={name:6}: Brier={bstr}  (样本{lr['n_samples']})")

    print("\n" + "=" * 55)
    print("按决策时点分层")
    print("=" * 55)
    for day in ["0", "3", "7", "14"]:
        dr = day_results[day]
        bstr = f"{dr['brier']:.4f}" if dr['brier'] is not None else "无样本"
        print(f"  解禁+{day:2}天: Brier={bstr}  (样本{dr['n_samples']})")

    # ==== 运行结束 + 耗时 ====
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print("\n" + "=" * 55)
    print(f"🕐 开始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🕐 结束: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱  总耗时: {duration:.0f} 秒 ({duration/60:.1f} 分钟)")
    print("=" * 55)

    # ==== 存结果到文件（保留历史，供以后对比）====
    results_dir = os.path.join("data", "backtest", "results")
    os.makedirs(results_dir, exist_ok=True)
    stamp = start_time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(results_dir, f"backtest_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_time": start_time.isoformat(),
            "duration_seconds": duration,
            "params": {"drift": DRIFT, "prior_strength": PRIOR_STRENGTH,
                       "n_sims": N_SIMS},
            "scope": "全样本(v1,未分组)",
            "overall_brier": overall_brier,
            "n_samples": len(all_pairs),
            "skipped": skipped,
            "by_n_layer": layer_results,
            "by_decision_day": day_results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n💾 结果已存: {out_path}")


if __name__ == "__main__":
    main()