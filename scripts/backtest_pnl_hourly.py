"""
PnL 策略1（持有到期）：每小时数据集，模拟真实盯盘交易。

交易规则（避免"钢镚陷阱"）：
  - n≥40（模型可靠）+ 价差≤10（买得到）
  - 胜率≥80% 且 买价<95¢（排除接近必然的钢镚门槛）且 edge≥5¢（有利润）
  - 一片一注：第一次满足的时刻，选 edge 最大的门槛下注
  - 持有到期，固定100张，结算时刻 = settle_date 14:00 UTC

用法：py -m scripts.backtest_pnl_hourly
切样本外：HOLDOUT_ONLY = True
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

SAMPLES_PATH = os.path.join("data", "backtest", "samples_pnl.csv")
HISTORICAL_DIR = os.path.join("data", "historical")
RESULTS_DIR = os.path.join("data", "backtest", "results", "pnl")

# ==== 参数 ====
DRIFT = 2.0
PRIOR_STRENGTH = 10.0
N_SIMS = 50_000
N_MIN = 80
WIN_PROB_MIN = 0.80      
WIN_PROB_MAX = 0.98
PRICE_MAX = 90
EDGE_MIN = 5
EDGE_MAX = 10
SPREAD_MAX = 5
VOLUME_MIN = 1000
DIRECTION = "both"       # "both" yes合约no合约都买/ "yes_only" / "no_only"
CONTRACTS = 100
INITIAL_CAPITAL = 1000.0

HOLDOUT_ONLY = True    # False就是全样本，True=只2026样本外
HOLDOUT_START = "2026-01-01"


class Tee:
    def __init__(self):
        self.terminal = sys.stdout
        self.buffer = io.StringIO()
    def write(self, msg):
        self.terminal.write(msg)
        self.buffer.write(msg)
    def flush(self):
        self.terminal.flush()


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
    start = datetime.now()
    tee = Tee()
    sys.stdout = tee

    scope = "2026样本外" if HOLDOUT_ONLY else "全样本"
    print(f"🕐 PnL策略1(持有到期) [{scope}]  {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"参数: drift={DRIFT} prior={PRIOR_STRENGTH} n≥{N_MIN} 胜率≥{WIN_PROB_MIN:.0%} 胜率≤{WIN_PROB_MAX:.0%} "
          f"买价<{PRICE_MAX}¢ edge≥{EDGE_MIN}¢ edge≤{EDGE_MAX}¢ 价差≤{SPREAD_MAX} {CONTRACTS}张 ${INITIAL_CAPITAL:.0f}\n")

    with open(SAMPLES_PATH, encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    print(f"读入 {len(all_rows)} 行\n")

    by_movie = defaultdict(list)
    for r in all_rows:
        by_movie[r["movie_key"]].append(r)

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
        # Kalshi 结算是严格大于：above 55 只有终值 >=56 才算 yes。
        # 所以获胜概率对齐为 P(score >= floor+1)。
        p = run_model(inp, n_sims=N_SIMS).prob_at_least(floor + 1)
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

        by_time = defaultdict(list)
        for r in rows:
            by_time[r["decision_time"]].append(r)

        for t_str in sorted(by_time.keys()):
            t_dt = parse_dt(t_str.replace(" ", "T") + ":00Z")
            if t_dt is None or t_dt >= settle_cutoff:
                continue

            candidates = []
            for r in by_time[t_str]:
                n_now = int(r["n_at_decision"])
                if n_now < N_MIN:
                    continue
                vol_raw = r.get("volume")
                vol_int = int(vol_raw) if str(vol_raw).isdigit() else 0
                if vol_int < VOLUME_MIN:
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
                prob_no = 1 - prob_yes
                edge_yes = prob_yes * 100 - yes_ask
                no_ask = 100 - yes_bid
                edge_no = prob_no * 100 - no_ask

                if (DIRECTION in ("both", "yes_only")
                        and WIN_PROB_MIN <= prob_yes <= WIN_PROB_MAX
                        and EDGE_MIN <= edge_yes <= EDGE_MAX and yes_ask < PRICE_MAX):
                    candidates.append({
                        "edge": edge_yes, "win_prob": prob_yes, "floor": floor,
                        "direction": "YES", "cost_c": yes_ask,
                        "won": result == "yes", "n": n_now, "volume": vol_int,
                        "yes_ask": yes_ask, "yes_bid": yes_bid,
                        "no_ask": 100 - yes_bid, "no_bid": 100 - yes_ask,
                        "final_score": r.get("final_score", ""),
                    })
                if (DIRECTION in ("both", "no_only")
                        and WIN_PROB_MIN <= prob_no <= WIN_PROB_MAX
                        and EDGE_MIN <= edge_no <= EDGE_MAX and no_ask < PRICE_MAX):
                    candidates.append({
                        "edge": edge_no, "win_prob": prob_no, "floor": floor,
                        "direction": "NO", "cost_c": no_ask,
                        "won": result == "no", "n": n_now, "volume": vol_int,
                        "yes_ask": yes_ask, "yes_bid": yes_bid,
                        "no_ask": no_ask, "no_bid": 100 - yes_ask,
                        "final_score": r.get("final_score", ""),
                    })

            if candidates:
                candidates.sort(key=lambda x: -x["edge"])
                best = candidates[0]
                best["movie"] = movie_key
                best["time"] = t_str
                best["settle_date"] = settle_date
                trades.append(best)
                break   # 一片一注

        movies_processed += 1
        if movies_processed % 30 == 0:
            print(f"  已处理 {movies_processed} 部，{len(trades)} 笔，缓存 {len(model_cache)}")

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

    print("\n按方向:")
    for d in ["YES", "NO"]:
        dt = [t for t in settled if t["direction"] == d]
        if dt:
            print(f"  {d}: {len(dt)}笔 胜{sum(1 for t in dt if t['won'])} "
                  f"盈亏${sum(t['pnl'] for t in dt):+.0f}")

    print("\n按胜率区间:")
    # 根据 WIN_PROB_MIN/MAX 自动切档（每档0.05宽）
    BUCKET = 0.05
    prob_bins = []
    lo = WIN_PROB_MIN
    while lo < WIN_PROB_MAX - 1e-9:
        hi = min(round(lo + BUCKET, 2), WIN_PROB_MAX)
        prob_bins.append((round(lo, 2), hi))
        lo = hi
    for lo, hi in prob_bins:
        if hi >= WIN_PROB_MAX - 1e-9:
            dt = [t for t in settled if lo <= t["win_prob"] <= hi]
        else:
            dt = [t for t in settled if lo <= t["win_prob"] < hi]
        if dt:
            w = sum(1 for t in dt if t["won"])
            print(f"  胜率{lo:.0%}-{hi:.0%}: {len(dt)}笔 "
                  f"实际胜{w}/{len(dt)} "
                  f"盈亏${sum(t['pnl'] for t in dt):+.0f}")

    print("\n按 edge 大小:")
    for lo, hi in [(5,10),(10,20),(20,40),(40,100)]:
        dt = [t for t in settled if lo <= t["edge"] < hi]
        if dt:
            print(f"  edge{lo}-{hi}¢: {len(dt)}笔 "
                  f"胜{sum(1 for t in dt if t['won'])} "
                  f"盈亏${sum(t['pnl'] for t in dt):+.0f}")

    print("\n前20笔交易明细:")
    for t in settled[:20]:
        print(f"  {t['movie'][:20]:20} {t['time']} floor={t['floor']:.0f} "
              f"{t['direction']} 胜率{t['win_prob']:.0%} edge{t['edge']:.0f}¢ "
              f"买价{t['cost_c']:.0f}¢ n={t['n']} {'✓' if t['won'] else '✗'} ${t['pnl']:+.0f}")

    dur = (datetime.now() - start).total_seconds()
    print(f"\n⏱ {dur:.0f}秒, 模型缓存{len(model_cache)}条")

    # 存 JSON + 完整报告TXT
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = start.strftime("%Y%m%d_%H%M%S")
    tag = "holdout" if HOLDOUT_ONLY else "full"
    with open(os.path.join(RESULTS_DIR, f"pnl_hourly_{tag}_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump({
            "scope": scope, "strategy": "hold_to_expiry",
            "params": {"drift": DRIFT, "prior": PRIOR_STRENGTH, "n_min": N_MIN,
                       "win_prob_min": WIN_PROB_MIN, "price_max": PRICE_MAX,
                       "edge_min": EDGE_MIN, "spread_max": SPREAD_MAX},
            "n_trades": n_tr, "wins": wins,
            "final_capital": round(capital, 2),
            "return_pct": round((capital/INITIAL_CAPITAL-1)*100, 2),
            "max_drawdown": round(mdd, 4),
            "trades": [{k:(round(v,3) if isinstance(v,float) else v)
                        for k,v in t.items()} for t in settled],
        }, f, ensure_ascii=False, indent=2)

    sys.stdout = tee.terminal
    report_path = os.path.join(RESULTS_DIR, f"report_pnl_{tag}_{stamp}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(tee.buffer.getvalue())
    print(f"💾 JSON + 完整报告已存: results/pnl/  ({report_path})")

    # 全字段交易记录 CSV
    import csv as csvmod
    csv_path = os.path.join(RESULTS_DIR, f"trades_{tag}_{stamp}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        if settled:
            writer = csvmod.writer(f)
            writer.writerow([
                "电影", "下注时刻", "门槛floor", "方向", "模型胜率", "edge",
                "买价cost_c", "决策时n", "成交量", "最终分",
                "yes_ask", "yes_bid", "no_ask", "no_bid",
                "是否赢", "盈亏pnl", "settle_date"
            ])
            for t in settled:
                writer.writerow([
                    t["movie"], t["time"], f"{t['floor']:.0f}", t["direction"],
                    f"{t['win_prob']:.3f}", f"{t['edge']:.1f}", f"{t['cost_c']:.0f}",
                    t["n"], t["volume"], t.get("final_score",""),
                    f"{t['yes_ask']:.0f}", f"{t['yes_bid']:.0f}",
                    f"{t['no_ask']:.0f}", f"{t['no_bid']:.0f}",
                    "赢" if t["won"] else "输", f"{t.get('pnl',0):.0f}", t["settle_date"],
                ])
    print(f"💾 全交易记录CSV: {csv_path}")


if __name__ == "__main__":
    main()