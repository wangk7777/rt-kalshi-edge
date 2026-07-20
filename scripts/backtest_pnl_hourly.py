"""
PnL v2
策略1（持有到期）：在每小时数据集上模拟真实"盯盘"交易。

规则（A1 - 第一次满足就下注，不用未来信息）：
  - 数据：samples_pnl.csv（每片每小时每门槛）
  - 过滤：decision_time < 结算时刻(settle_date 14:00 UTC) + n≥40 + 价差≤10
  - 一片一注：按时间遍历，第一次出现"有门槛 胜率≥80% 且 edge>0"时，
    在该时刻选胜率最高的门槛下注，之后该片不再交易
  - 胜率 = 模型概率（YES用prob，NO用1-prob）
  - 持有到期，固定100张，按 result 结算
  - 按结算时间滚动资金

用法：py -m scripts.backtest_pnl_hourly
切样本外：HOLDOUT_ONLY = True
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
RESULTS_DIR = os.path.join("data", "backtest", "results", "pnl")

# ==== 参数 ====
DRIFT = 4.0
PRIOR_STRENGTH = 15.0
N_SIMS = 50_000
N_MIN = 40                # 只在评论数≥40时交易
WIN_PROB_MIN = 0.80       # 胜率≥80%才考虑
SPREAD_MAX = 10
CONTRACTS = 100
INITIAL_CAPITAL = 1000.0

HOLDOUT_ONLY = False      # True=只2026样本外
HOLDOUT_START = "2026-01-01"


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
    settle = settle.replace(hour=14)  # 14:00 UTC
    return sum(1 for r in reviews
               if parse_dt(r.get("date")) and parse_dt(r["date"]) <= settle)


def main():
    start = datetime.now()
    scope = "2026样本外" if HOLDOUT_ONLY else "全样本"
    print(f"🕐 PnL策略1(持有到期) [{scope}]  {start.strftime('%H:%M:%S')}")
    print(f"参数: drift={DRIFT} prior={PRIOR_STRENGTH} n≥{N_MIN} 胜率≥{WIN_PROB_MIN:.0%} "
          f"价差≤{SPREAD_MAX} {CONTRACTS}张 ${INITIAL_CAPITAL:.0f}\n")

    with open(SAMPLES_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
    print(f"读入 {len(all_rows)} 行\n")

    # 按电影分组，每片内按时间排序
    by_movie = defaultdict(list)
    for r in all_rows:
        by_movie[r["movie_key"]].append(r)

    n_final_cache = {}
    model_cache = {}

    def model_prob(score, n, base_rate, floor):
        key = (score, n, base_rate, floor)
        if key in model_cache:
            return model_cache[key]
        nf = n_final_this
        inp = ModelInputs(score_now=score, n_now=n, base_rate=base_rate,
                          prior_strength=PRIOR_STRENGTH, n_final=max(nf, n), drift=DRIFT)
        p = run_model(inp, n_sims=N_SIMS).prob_at_least(floor)
        model_cache[key] = p
        return p

    trades = []
    movies_processed = 0

    for movie_key, rows in by_movie.items():
        settle_date = rows[0]["settle_date"]
        if HOLDOUT_ONLY and settle_date < HOLDOUT_START:
            continue
        settle_cutoff = parse_dt(settle_date + "T00:00:00Z")
        if settle_cutoff is None:
            continue
        settle_cutoff = settle_cutoff.replace(hour=14)

        if movie_key not in n_final_cache:
            n_final_cache[movie_key] = compute_n_final(movie_key, settle_date)
        n_final_this = n_final_cache[movie_key]
        if n_final_this is None:
            continue
        base_rate = float(rows[0]["base_rate"])
        final_score = rows[0]["final_score"]

        # 按时间排序所有(时刻,门槛)行
        rows_sorted = sorted(rows, key=lambda r: r["decision_time"])

        # 按时刻分组（同一时刻有多个门槛）
        by_time = defaultdict(list)
        for r in rows_sorted:
            by_time[r["decision_time"]].append(r)

        # 按时间遍历，找第一个满足条件的时刻（A1）
        traded = False
        for t_str in sorted(by_time.keys()):
            t_dt = parse_dt(t_str.replace(" ", "T") + ":00Z")
            if t_dt is None or t_dt >= settle_cutoff:
                continue   # 结算后不交易

            candidates = []   # (胜率, 门槛行, 方向, edge, 买价)
            for r in by_time[t_str]:
                n_now = int(r["n_at_decision"])
                if n_now < N_MIN:
                    continue
                spread = r.get("spread")
                if spread == "" or spread is None or float(spread) > SPREAD_MAX:
                    continue
                yes_ask = float(r["yes_ask"]) if r["yes_ask"] else None
                yes_bid = float(r["yes_bid"]) if r["yes_bid"] else None
                if yes_ask is None or yes_bid is None:
                    continue
                floor = float(r["floor"])
                result = r["result"]
                if result not in ("yes", "no"):
                    continue
                score = float(r["score_at_decision"])

                prob_yes = model_prob(score, n_now, base_rate, floor)

                # YES方向：胜率=prob_yes，edge=prob_yes*100 - yes_ask
                edge_yes = prob_yes * 100 - yes_ask
                # NO方向：胜率=1-prob_yes，edge=(1-prob_yes)*100 - (100-yes_bid)
                prob_no = 1 - prob_yes
                edge_no = prob_no * 100 - (100 - yes_bid)

                # 只要 胜率≥阈值 且 edge>0
                if prob_yes >= WIN_PROB_MIN and edge_yes > 0:
                    candidates.append((prob_yes, floor, "YES", edge_yes, yes_ask,
                                       result == "yes", n_now, r.get("volume","")))
                if prob_no >= WIN_PROB_MIN and edge_no > 0:
                    candidates.append((prob_no, floor, "NO", edge_no, 100 - yes_bid,
                                       result == "no", n_now, r.get("volume","")))

            if candidates:
                # 选胜率最高的（最稳）
                candidates.sort(key=lambda x: -x[0])
                win_p, floor, direction, edge, cost_c, won, n_now, vol = candidates[0]
                trades.append({
                    "movie": movie_key, "time": t_str, "floor": floor,
                    "direction": direction, "win_prob": win_p, "edge": edge,
                    "cost_c": cost_c, "won": won, "n": n_now, "volume": vol,
                    "settle_date": settle_date,
                })
                traded = True
                break   # 一片一注，之后不再交易这片

        movies_processed += 1
        if movies_processed % 30 == 0:
            print(f"  已处理 {movies_processed} 部，{len(trades)} 笔交易，"
                  f"缓存 {len(model_cache)}")

    # 滚动结算
    trades.sort(key=lambda t: t["settle_date"])
    capital = INITIAL_CAPITAL
    equity = [("start", capital)]
    wins = 0
    staked = 0
    for t in trades:
        cost = t["cost_c"] * CONTRACTS / 100
        if cost > capital:
            continue
        payout = 100 * CONTRACTS / 100 if t["won"] else 0
        pnl = payout - cost
        capital += pnl
        staked += cost
        t["pnl"] = pnl
        if t["won"]:
            wins += 1
        equity.append((t["settle_date"], round(capital, 2)))

    settled = [t for t in trades if "pnl" in t]
    n_tr = len(settled)
    losses = n_tr - wins

    print("\n" + "=" * 60)
    print(f"[{scope}] 交易 {n_tr} 笔 (胜{wins} 负{losses})")
    if n_tr:
        print(f"胜率: {wins/n_tr*100:.1f}%")
    print(f"初始 ${INITIAL_CAPITAL:.2f} → 最终 ${capital:.2f} "
          f"({(capital/INITIAL_CAPITAL-1)*100:+.1f}%)")
    if staked:
        print(f"回报率(盈亏/下注): {(capital-INITIAL_CAPITAL)/staked*100:+.1f}%")
    peak = INITIAL_CAPITAL
    mdd = 0
    for _, e in equity:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak)
    print(f"最大回撤: {mdd*100:.1f}%")
    print("=" * 60)

    # 分解
    print("\n按方向:")
    for d in ["YES", "NO"]:
        dt = [t for t in settled if t["direction"] == d]
        if dt:
            print(f"  {d}: {len(dt)}笔 胜{sum(1 for t in dt if t['won'])} "
                  f"盈亏${sum(t['pnl'] for t in dt):+.0f}")

    print("\n按胜率区间:")
    for lo, hi in [(0.85,0.90),(0.90,0.95),(0.95,1.01)]:
        dt = [t for t in settled if lo <= t["win_prob"] < hi]
        if dt:
            print(f"  胜率{lo:.0%}-{hi:.0%}: {len(dt)}笔 "
                  f"实际胜{sum(1 for t in dt if t['won'])}/{len(dt)} "
                  f"盈亏${sum(t['pnl'] for t in dt):+.0f}")

    print("\n入场时机（解禁后多久下注）:")
    print("  (time列是下注时刻，可查每笔何时入场)")
    print("\n前15笔交易明细:")
    for t in settled[:15]:
        print(f"  {t['movie'][:20]:20} {t['time']} floor={t['floor']:.0f} "
              f"{t['direction']} 胜率{t['win_prob']:.0%} edge{t['edge']:.0f}¢ "
              f"n={t['n']} {'✓' if t['won'] else '✗'} ${t['pnl']:+.0f}")

    dur = (datetime.now() - start).total_seconds()
    print(f"\n⏱ {dur:.0f}秒, 模型缓存{len(model_cache)}条")

    # 存
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = start.strftime("%Y%m%d_%H%M%S")
    tag = "holdout" if HOLDOUT_ONLY else "full"
    with open(os.path.join(RESULTS_DIR, f"pnl_hourly_{tag}_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump({
            "scope": scope, "strategy": "hold_to_expiry",
            "params": {"drift": DRIFT, "prior": PRIOR_STRENGTH, "n_min": N_MIN,
                       "win_prob_min": WIN_PROB_MIN, "spread_max": SPREAD_MAX},
            "n_trades": n_tr, "wins": wins,
            "final_capital": round(capital, 2),
            "return_pct": round((capital/INITIAL_CAPITAL-1)*100, 2),
            "max_drawdown": round(mdd, 4),
            "trades": [{k:(round(v,3) if isinstance(v,float) else v)
                        for k,v in t.items()} for t in settled],
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 已存 results/pnl/")


if __name__ == "__main__":
    main()