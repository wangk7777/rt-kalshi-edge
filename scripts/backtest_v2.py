"""
回测 v2：扫参数校准 + 验证。

流程：
  1. 在【校准组】(2024+2025上半年) 扫 drift×prior 网格，
     用目标C(校准误差为主+Brier参考)找最优参数。
  2. 在【验证组】(2025下半年，校准时没碰过) 用最优参数验证。
  3. 【样本外】(2026) 留作最终检验。
目标：看调参数能不能把 v1 发现的"系统性高估"校准掉。

用法：py -m scripts.backtest_v2
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from src.model.bayesian import ModelInputs, run_model

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
        prob = res.prob_at_least(s["floor"])
        pairs.append((prob, 1 if s["result"] == "yes" else 0))
    return pairs


def main():
    start = datetime.now()
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

    # ===== 在校准组扫参数 =====
    print("=" * 55)
    print(f"在校准组扫参数 ({len(DRIFT_GRID)}×{len(PRIOR_GRID)}={len(DRIFT_GRID)*len(PRIOR_GRID)}组)")
    print("=" * 55)

    grid_results = []
    best = None
    for drift in DRIFT_GRID:
        for prior in PRIOR_GRID:
            pairs = run_params(groups["calib"], drift, prior)
            ce = calibration_error(pairs)
            br = brier(pairs)
            sc = score_C(pairs)
            grid_results.append({"drift": drift, "prior": prior,
                                 "calib_error": ce, "brier": br, "score_C": sc})
            marker = ""
            if best is None or sc < best["score_C"]:
                best = grid_results[-1]
                marker = " ← 目前最优"
            print(f"  drift={drift} prior={prior:2}: "
                  f"校准误差={ce:.4f} Brier={br:.4f} 综合={sc:.4f}{marker}")

    print(f"\n🏆 最优参数: drift={best['drift']}, prior={best['prior']}")
    print(f"   (校准误差={best['calib_error']:.4f}, Brier={best['brier']:.4f})")

    # ===== 用最优参数在验证组验证 =====
    print("\n" + "=" * 55)
    print("用最优参数在【验证组】验证（校准时没碰过）")
    print("=" * 55)
    valid_pairs = run_params(groups["valid"], best["drift"], best["prior"])
    valid_ce = calibration_error(valid_pairs)
    valid_br = brier(valid_pairs)
    print(f"验证组 校准误差={valid_ce:.4f}  Brier={valid_br:.4f}")
    print("\n验证组校准曲线:")
    for row in calibration_table(valid_pairs):
        bar = "█" * int(row["actual_freq"] * 30)
        print(f"  预测[{row['bin']}] 均值{row['pred_mean']:.2f} "
              f"→ 实际{row['actual_freq']:.2f} (n={row['n']:4}) {bar}")

    # ===== 对比：旧参数(drift=2,prior=10)在验证组 =====
    print("\n对比：旧参数 drift=2,prior=10 在验证组:")
    old_pairs = run_params(groups["valid"], 2, 10)
    print(f"  旧参数 校准误差={calibration_error(old_pairs):.4f}  Brier={brier(old_pairs):.4f}")
    print(f"  新参数 校准误差={valid_ce:.4f}  Brier={valid_br:.4f}")
    improve = calibration_error(old_pairs) - valid_ce
    print(f"  校准误差改善: {improve:+.4f} ({'变好' if improve>0 else '变差'})")

    end = datetime.now()
    duration = (end - start).total_seconds()
    print(f"\n⏱  总耗时: {duration:.0f}秒 ({duration/60:.1f}分钟)")

    # ===== 存 JSON(全量) + TXT(可读) =====
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = start.strftime("%Y%m%d_%H%M%S")

    json_path = os.path.join(RESULTS_DIR, f"v2_{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_time": start.isoformat(), "duration_seconds": duration,
            "n_sims": N_SIMS,
            "group_sizes": {k: len(v) for k, v in groups.items()},
            "grid_results": grid_results,
            "best_params": best,
            "validation": {
                "calib_error": valid_ce, "brier": valid_br,
                "calibration_table": calibration_table(valid_pairs),
            },
            "old_params_on_valid": {
                "calib_error": calibration_error(old_pairs),
                "brier": brier(old_pairs),
            },
        }, f, ensure_ascii=False, indent=2)

    txt_path = os.path.join(RESULTS_DIR, f"v2_{stamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"回测 v2 报告  {start.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 55 + "\n\n")
        f.write(f"最优参数: drift={best['drift']}, prior={best['prior']}\n")
        f.write(f"  校准组: 校准误差={best['calib_error']:.4f} Brier={best['brier']:.4f}\n")
        f.write(f"  验证组: 校准误差={valid_ce:.4f} Brier={valid_br:.4f}\n\n")
        f.write(f"对比旧参数(drift=2,prior=10)验证组校准误差={calibration_error(old_pairs):.4f}\n")
        f.write(f"改善: {improve:+.4f}\n\n")
        f.write("验证组校准曲线:\n")
        for row in calibration_table(valid_pairs):
            f.write(f"  预测[{row['bin']}] 均值{row['pred_mean']:.2f} "
                    f"→ 实际{row['actual_freq']:.2f} (n={row['n']})\n")

    print(f"\n💾 JSON(全量): {json_path}")
    print(f"💾 TXT(可读): {txt_path}")


if __name__ == "__main__":
    main()