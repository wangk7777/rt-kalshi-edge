"""
诊断大edge：找出所有 edge>阈值 的时刻，列出真实盘口 + 模型判断 + 最终对错。
用于判断"大edge是散户定错价(真机会)还是模型错(幻觉)"。

独立诊断脚本，不做交易模拟。扫全部样本（不受PnL交易规则限制）。

用法：py -m scripts.diagnose_big_edge
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from src.model.bayesian import ModelInputs, run_model

SAMPLES_PATH = os.path.join("data", "backtest", "samples_pnl.csv")
HISTORICAL_DIR = os.path.join("data", "historical")

# ==== 可调参数 ====
DRIFT = 4.0
PRIOR_STRENGTH = 15.0
N_SIMS = 50_000
EDGE_MIN = 20              # 找 edge > 此值 的
N_MIN = 40                # 只看 n≥此值（模型可靠区，排除n小时的噪声）
VOLUME_MIN = 3000            # 只看成交量≥此值（可设高一点只看活跃盘口）
HOLDOUT_ONLY = False


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
    settle = parse_dt(settle_date_str + "T00:00:00Z")
    if settle is None:
        return len(reviews)
    settle = settle.replace(hour=14)
    return sum(1 for r in reviews
               if parse_dt(r.get("date")) and parse_dt(r["date"]) <= settle)


def main():
    with open(SAMPLES_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # 为避免同一门槛在很多小时重复出现，每个(电影,门槛)只取"第一次出现大edge"的时刻
    n_final_cache = {}
    model_cache = {}
    n_final_this = None

    def model_prob(score, n, base_rate, floor):
        key = (score, n, base_rate, floor)
        if key in model_cache:
            return model_cache[key]
        inp = ModelInputs(score_now=score, n_now=n, base_rate=base_rate,
                          prior_strength=PRIOR_STRENGTH,
                          n_final=max(n_final_this, n), drift=DRIFT)
        p = run_model(inp, n_sims=N_SIMS).prob_at_least(floor+1)
        model_cache[key] = p
        return p

    seen = set()   # (movie, floor, direction) 只记第一次
    big_edges = []

    # 按电影+时间排序，保证"第一次"是最早的
    rows.sort(key=lambda r: (r["movie_key"], r["decision_time"]))

    for r in rows:
        mk = r["movie_key"]
        settle_date = r["settle_date"]
        if HOLDOUT_ONLY and settle_date < "2026-01-01":
            continue
        n_now = int(r["n_at_decision"])
        if n_now < N_MIN:
            continue
        vol = r.get("volume")
        vol = int(vol) if str(vol).isdigit() else 0
        if vol < VOLUME_MIN:
            continue
        yes_ask = float(r["yes_ask"]) if r["yes_ask"] else None
        yes_bid = float(r["yes_bid"]) if r["yes_bid"] else None
        if yes_ask is None or yes_bid is None:
            continue
        spread = float(r["spread"]) if r["spread"] else None
        floor = float(r["floor"])
        result = r["result"]
        if result not in ("yes", "no"):
            continue
        score = float(r["score_at_decision"])
        base_rate = float(r["base_rate"])

        if mk not in n_final_cache:
            n_final_cache[mk] = compute_n_final(mk, settle_date)
        n_final_this = n_final_cache[mk]
        if n_final_this is None:
            continue

        prob_yes = model_prob(score, n_now, base_rate, floor)
        prob_no = 1 - prob_yes
        edge_yes = prob_yes * 100 - yes_ask
        edge_no = prob_no * 100 - (100 - yes_bid)

        for direction, edge, prob, won in [
            ("YES", edge_yes, prob_yes, result == "yes"),
            ("NO", edge_no, prob_no, result == "no"),
        ]:
            if edge <= EDGE_MIN:
                continue
            key = (mk, floor, direction)
            if key in seen:
                continue
            seen.add(key)
            big_edges.append({
                "movie": mk, "time": r["decision_time"], "floor": floor,
                "direction": direction, "edge": edge, "model_prob": prob,
                "yes_ask": yes_ask, "yes_bid": yes_bid, "spread": spread,
                "volume": vol, "n": n_now, "score": score,
                "final_score": r["final_score"], "result": result, "won": won,
                "settle_date": settle_date,
            })

    # ===== 输出 =====
    big_edges.sort(key=lambda x: -x["edge"])
    scope = "2026样本外" if HOLDOUT_ONLY else "全样本"
    print(f"大edge诊断 [{scope}]: edge>{EDGE_MIN}, n≥{N_MIN}, vol≥{VOLUME_MIN}")
    print(f"共找到 {len(big_edges)} 个大edge时刻\n")

    # 关键统计：大edge最后对不对
    won_count = sum(1 for e in big_edges if e["won"])
    total = len(big_edges)
    if total:
        print(f"★ 大edge最终对错: {won_count}/{total} 正确 ({won_count/total*100:.0f}%)")
        print(f"  若正确率高→散户定错价，是真机会（你的信念成立）")
        print(f"  若正确率低→模型在极端分歧时错，大edge是幻觉\n")

    # 按成交量分层看正确率（你的核心假设：高成交量盘口大edge是散户定错）
    print("按成交量分层的大edge正确率:")
    for lo, hi, name in [(0,100,"<100"),(100,1000,"100-1k"),(1000,10000,"1k-10k"),(10000,10**9,"10k+")]:
        grp = [e for e in big_edges if lo <= e["volume"] < hi]
        if grp:
            w = sum(1 for e in grp if e["won"])
            print(f"  成交量{name:8}: {len(grp):3}个, 正确{w}/{len(grp)} ({w*100//len(grp)}%)")

    # 明细
    print(f"\n所有大edge明细（按edge降序）:")
    print(f"{'电影':22}{'时刻':17}{'门槛':>5}{'方向':>4}{'edge':>5}{'模型%':>6}"
          f"{'ask':>4}{'bid':>4}{'量':>7}{'n':>4}{'最终分':>6}{'结果':>4}{'对?':>4}")
    for e in big_edges:
        print(f"{e['movie'][:20]:22}{e['time']:17}{e['floor']:>5.0f}{e['direction']:>4}"
              f"{e['edge']:>5.0f}{e['model_prob']*100:>6.0f}{e['yes_ask']:>4.0f}"
              f"{e['yes_bid']:>4.0f}{e['volume']:>7}{e['n']:>4}"
              f"{str(e['final_score']):>6}{e['result']:>4}{'✓' if e['won'] else '✗':>4}")

    # 存
    out_dir = os.path.join("data", "backtest", "results", "diagnostics")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(out_dir, f"big_edge_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump({"params": {"edge_min": EDGE_MIN, "n_min": N_MIN,
                              "volume_min": VOLUME_MIN, "scope": scope},
                   "total": total, "correct": won_count,
                   "big_edges": [{k:(round(v,2) if isinstance(v,float) else v)
                                  for k,v in e.items()} for e in big_edges]},
                  f, ensure_ascii=False, indent=2)
    print(f"\n💾 已存 results/diagnostics/")

    # ===== 存 CSV（方便Excel查看）=====
    out_dir = os.path.join("data", "backtest", "results", "diagnostics")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "holdout" if HOLDOUT_ONLY else "full"
    csv_path = os.path.join(out_dir, f"big_edge_{tag}_{stamp}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        # utf-8-sig 让 Excel 正确显示中文
        writer = csv.writer(f)
        # 表头
        writer.writerow([
            "电影", "时刻", "门槛floor", "方向", "edge",
            "模型胜率%", "yes_ask", "yes_bid", "价差", "成交量",
            "决策时n", "决策时score", "最终分", "结算result", "是否正确",
            "settle_date"
        ])
        for e in big_edges:
            writer.writerow([
                e["movie"], e["time"], f"{e['floor']:.0f}", e["direction"],
                f"{e['edge']:.1f}", f"{e['model_prob']*100:.0f}",
                f"{e['yes_ask']:.0f}", f"{e['yes_bid']:.0f}",
                f"{e['spread']:.0f}" if e["spread"] is not None else "",
                e["volume"], e["n"], f"{e['score']:.1f}",
                e["final_score"], e["result"],
                "对" if e["won"] else "错",
                e["settle_date"],
            ])

    print(f"\n💾 CSV已存: {csv_path}")
    if total:
        print(f"   共{total}个大edge，正确{won_count} ({won_count/total*100:.0f}%)")


if __name__ == "__main__":
    main()