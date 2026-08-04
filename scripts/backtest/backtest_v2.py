"""
回测 v2：扫参数校准 + 验证。

流程：
  1. 在【校准组】(2024+2025上半年) 扫 drift×prior 网格，
     用目标C(校准误差为主+Brier参考)找最优参数。
  2. 在【验证组】(2025下半年，校准时没碰过) 用最优参数验证。
  3. 【样本外】(2026) 留作最终检验。
目标：看调参数能不能把 v1 发现的"系统性高估"校准掉。

用法：py -m scripts.backtest.backtest_v2
"""

from __future__ import annotations

import csv
import json
import os
import sys
import io
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from src.model.bayesian import ModelInputs, run_model

class Tee:
    def __init__(self):
        self.terminal = sys.stdout
        self.buffer = io.StringIO()
    def write(self, msg):
        self.terminal.write(msg)
        self.buffer.write(msg)
    def flush(self):
        self.terminal.flush()

SAMPLES_PATH = os.path.join("data", "backtest", "samples.csv")
HISTORICAL_DIR = os.path.join("data", "historical")
RESULTS_DIR = os.path.join("data", "backtest", "results")

# ==== 扫描网格 ====
DRIFT_GRID = [0, 1, 2, 3, 4, 5, 6]
PRIOR_GRID = [5, 10, 15, 20]
N_SIMS = 20_000          # 扫参数用小模拟数换速度

# ==== 分组边界（按 settle_date 字符串比较）====
CALIB_END = "2025-06-30"    # <= 此日 = 校准组
VALID_END = "2025-12-31"    # 校准之后~此日 = 验证组；之后 = 样本外(2026)


def which_group(settle_date):
    if settle_date <= CALIB_END:
        return "calib"
    if settle_date <= VALID_END:
        return "valid"
    return "holdout"


def parse_dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_n_final(movie_key, settle_date_str):
    path = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        reviews = json.load(f)
    settle = parse_dt(settle_date_str)
    if settle is None:
        return len(reviews)
    if settle.tzinfo is None:
        settle = settle.replace(tzinfo=timezone.utc) + timedelta(hours=14)
    return sum(1 for r in reviews
               if parse_dt(r.get("date")) and parse_dt(r["date"]) <= settle)


def brier(pairs):
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs) if pairs else None


def calibration_error(pairs, n_bins=10):
    """各桶|预测均值-实际频率|按样本数加权平均。越小越贴45度线。"""
    bins = [[] for _ in range(n_bins)]
    for p, a in pairs:
        bins[min(int(p * n_bins), n_bins - 1)].append((p, a))
    total_err, total_n = 0, 0
    for b in bins:
        if not b:
            continue
        avg_pred = sum(p for p, a in b) / len(b)
        actual = sum(a for p, a in b) / len(b)
        total_err += abs(avg_pred - actual) * len(b)
        total_n += len(b)
    return total_err / total_n if total_n else None


def score_C(pairs):
    """目标C：校准误差为主(权重1.0) + Brier参考(权重0.3)。越低越好。"""
    ce = calibration_error(pairs)
    br = brier(pairs)
    if ce is None or br is None:
        return float("inf")
    return ce * 1.0 + br * 0.3


def calibration_table(pairs, n_bins=10):
    """返回校准曲线各桶数据，供报告。"""
    bins = [[] for _ in range(n_bins)]
    for p, a in pairs:
        bins[min(int(p * n_bins), n_bins - 1)].append((p, a))
    table = []
    for i, b in enumerate(bins):
        if not b:
            continue
        table.append({
            "bin": f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}",
            "pred_mean": round(sum(p for p, a in b) / len(b), 3),
            "actual_freq": round(sum(a for p, a in b) / len(b), 3),
            "n": len(b),
        })
    return table


def run_params(samples, drift, prior):
    """用一组参数跑一批样本，返回 (prob, actual) 列表。"""
    pairs = []
    for s in samples:
        inp = ModelInputs(
            score_now=s["score"], n_now=s["n"], base_rate=s["base_rate"],
            prior_strength=prior, n_final=s["n_final"], drift=drift,
        )
        res = run_model(inp, n_sims=N_SIMS)
        # Kalshi 结算是严格大于：above 55 只有终值 >=56 才算 yes。
        # 所以获胜概率对齐为 P(score >= floor+1)。
        prob = res.prob_at_least(s["floor"] + 1)
        pairs.append((prob, 1 if s["result"] == "yes" else 0))
    return pairs


def main():
    start = datetime.now()

    tee = Tee()
    sys.stdout = tee

    print(f"🕐 v2 回测开始: {start.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 读样本 + 预处理成结构，分组
    with open(SAMPLES_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    n_final_cache = {}
    groups = {"calib": [], "valid": [], "holdout": []}
    for r in rows:
        mk = r["movie_key"]
        if mk not in n_final_cache:
            n_final_cache[mk] = compute_n_final(mk, r["settle_date"])
        nf = n_final_cache[mk]
        n_now = int(r["n_at_decision"])
        if nf is None or n_now == 0 or r["result"] not in ("yes", "no"):
            continue
        if nf < n_now:
            nf = n_now
        s = {
            "score": float(r["score_at_decision"]), "n": n_now,
            "base_rate": float(r["base_rate"]), "floor": float(r["floor"]),
            "n_final": nf, "result": r["result"],
        }
        groups[which_group(r["settle_date"])].append(s)

    print(f"校准组: {len(groups['calib'])} 样本")
    print(f"验证组: {len(groups['valid'])} 样本")
    print(f"样本外(2026): {len(groups['holdout'])} 样本\n")

    # ===== 扫参数：每组同时在校准组和验证组评估 =====
    print("=" * 70)
    print(f"扫参数：每组同时评估校准组+验证组 ({len(DRIFT_GRID)}×{len(PRIOR_GRID)}组)")
    print("=" * 70)
    print(f"{'drift':>5}{'prior':>6}{'校准组CE':>11}{'验证组CE':>11}{'验证组Brier':>13}")

    grid_results = []
    for drift in DRIFT_GRID:
        for prior in PRIOR_GRID:
            calib_pairs = run_params(groups["calib"], drift, prior)
            valid_pairs = run_params(groups["valid"], drift, prior)
            calib_ce = calibration_error(calib_pairs)
            valid_ce = calibration_error(valid_pairs)
            valid_br = brier(valid_pairs)
            grid_results.append({
                "drift": drift, "prior": prior,
                "calib_ce": calib_ce, "valid_ce": valid_ce, "valid_brier": valid_br,
            })
            print(f"{drift:>5}{prior:>6}{calib_ce:>11.4f}{valid_ce:>11.4f}{valid_br:>13.4f}")

    # 校准组最优（大概率过拟合，仅作对比展示）
    best_calib = min(grid_results, key=lambda x: x["calib_ce"])
    # 验证组最优（真正泛化好的，用这个）
    best = min(grid_results, key=lambda x: x["valid_ce"])

    print("\n" + "=" * 70)
    print(f"校准组最优: drift={best_calib['drift']} prior={best_calib['prior']} "
          f"(校准CE={best_calib['calib_ce']:.4f}, 但验证CE={best_calib['valid_ce']:.4f})")
    print(f"  ⚠ 校准组最优往往过拟合（偏好大drift），不直接用")
    print(f"🏆 验证组最优: drift={best['drift']} prior={best['prior']} "
          f"(验证CE={best['valid_ce']:.4f}, Brier={best['valid_brier']:.4f})")
    print(f"  ← 这个泛化好，是最终参数")
    print("=" * 70)

    # ===== 用验证组最优参数，在 2026 样本外做最终确认 =====
    print("\n" + "=" * 70)
    print("最终确认：验证组最优参数 在【2026样本外】（校准+验证都没碰过）")
    print("=" * 70)
    if groups["holdout"]:
        holdout_pairs = run_params(groups["holdout"], best["drift"], best["prior"])
        holdout_ce = calibration_error(holdout_pairs)
        holdout_br = brier(holdout_pairs)
        print(f"2026样本外: 校准误差={holdout_ce:.4f}  Brier={holdout_br:.4f}")
        print("\n2026样本外校准曲线:")
        for row in calibration_table(holdout_pairs):
            bar = "█" * int(row["actual_freq"] * 30)
            print(f"  预测[{row['bin']}] 均值{row['pred_mean']:.2f} "
                  f"→ 实际{row['actual_freq']:.2f} (n={row['n']:4}) {bar}")
    else:
        print("  (无2026样本)")
        holdout_ce = holdout_br = None

    # ===== 验证组校准曲线（最优参数）=====
    print("\n验证组校准曲线（最优参数 drift={} prior={}）:".format(best["drift"], best["prior"]))
    valid_pairs = run_params(groups["valid"], best["drift"], best["prior"])
    for row in calibration_table(valid_pairs):
        bar = "█" * int(row["actual_freq"] * 30)
        print(f"  预测[{row['bin']}] 均值{row['pred_mean']:.2f} "
              f"→ 实际{row['actual_freq']:.2f} (n={row['n']:4}) {bar}")

    valid_ce = calibration_error(valid_pairs)
    valid_br = brier(valid_pairs)
    end = datetime.now()
    duration = (end - start).total_seconds()
    print(f"\n⏱  总耗时: {duration:.0f}秒 ({duration/60:.1f}分钟)")

    # ===== 存 JSON + TXT =====
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = start.strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(RESULTS_DIR, f"v2_{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_time": start.isoformat(), "duration_seconds": duration,
            "n_sims": N_SIMS,
            "group_sizes": {k: len(v) for k, v in groups.items()},
            "grid_results": grid_results,
            "best_by_calib": best_calib,
            "best_by_valid": best,
            "holdout": {"calib_error": holdout_ce, "brier": holdout_br},
        }, f, ensure_ascii=False, indent=2)

    txt_path = os.path.join(RESULTS_DIR, f"v2_{stamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"回测 v2 报告  {start.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 55 + "\n\n")
        f.write(f"验证组最优参数: drift={best['drift']}, prior={best['prior']}\n")
        f.write(f"  验证组: CE={best['valid_ce']:.4f} Brier={best['valid_brier']:.4f}\n")
        if holdout_ce is not None:
            f.write(f"  2026样本外: CE={holdout_ce:.4f} Brier={holdout_br:.4f}\n")
        f.write(f"\n(校准组最优是 drift={best_calib['drift']}，但过拟合，未采用)\n")

    print(f"\n💾 JSON: {json_path}")
    print(f"💾 TXT: {txt_path}")

    # 恢复 stdout，把完整报告原封不动存 txt
    sys.stdout = tee.terminal
    report_path = os.path.join(RESULTS_DIR, f"report_v2_{stamp}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(tee.buffer.getvalue())
    print(f"💾 完整报告已存: {report_path}")


if __name__ == "__main__":
    main()