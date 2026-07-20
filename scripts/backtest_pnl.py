"""
PnL 盈亏模拟：用验证好的 drift=4/prior=15，模拟按模型信号交易。
可切换"全样本"或"仅2026样本外"。

规则：+3天、每部片选|edge|最大的1门槛、双向、固定100张、edge≥阈值、
      market还开着、流动性spread≤10。按settle_date时间顺序滚动结算。

用法：py -m scripts.backtest_pnl
切换样本外：把 HOLDOUT_ONLY 改成 True
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
RESULTS_DIR = os.path.join("data", "backtest", "results", "pnl")

# ==== 交易参数 ====
DRIFT = 4.0
PRIOR_STRENGTH = 15.0
N_SIMS = 50_000
DECISION_DAY = "0"
EDGE_THRESHOLD = 10
CONTRACTS = 100
SPREAD_MAX = 10
INITIAL_CAPITAL = 1000.0

# ==== 样本范围 ====
HOLDOUT_ONLY = False         # True=只用2026样本外; False=全样本
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
    settle = parse_dt(settle_date_str)
    if settle is None:
        return len(reviews)
    if settle.tzinfo is None:
        settle = settle.replace(tzinfo=timezone.utc) + timedelta(hours=14)
    return sum(1 for r in reviews
               if parse_dt(r.get("date")) and parse_dt(r["date"]) <= settle)


def main():
    start = datetime.now()
    scope = "2026样本外" if HOLDOUT_ONLY else "全样本"
    print(f"🕐 PnL模拟开始: {start.strftime('%Y-%m-%d %H:%M:%S')}  [{scope}]")
    print(f"参数: drift={DRIFT}, prior={PRIOR_STRENGTH}, +{DECISION_DAY}天, "
          f"edge≥{EDGE_THRESHOLD}¢, {CONTRACTS}张/笔, 初始${INITIAL_CAPITAL:.0f}\n")

    with open(SAMPLES_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    candidates = []
    for r in rows:
        if r["decision_day"] != DECISION_DAY:
            continue
        if HOLDOUT_ONLY and r["settle_date"] < HOLDOUT_START:
            continue
        if r["decision_date"] >= r["settle_date"]:   # market已结算
            continue
        spread = r.get("spread")
        if spread == "" or spread is None or float(spread) > SPREAD_MAX:
            continue
        candidates.append(r)

    print(f"{scope} +{DECISION_DAY}天可交易样本: {len(candidates)} 行\n")

    n_final_cache = {}
    for r in candidates:
        mk = r["movie_key"]
        if mk not in n_final_cache:
            n_final_cache[mk] = compute_n_final(mk, r["settle_date"])

    by_movie = defaultdict(list)
    for r in candidates:
        by_movie[r["movie_key"]].append(r)

    trades = []
    for mk, mk_rows in by_movie.items():
        n_final = n_final_cache.get(mk)
        if n_final is None:
            continue
        best = None
        for r in mk_rows:
            n_now = int(r["n_at_decision"])
            if n_now == 0:
                continue
            nf = max(n_final, n_now)
            score = float(r["score_at_decision"])
            base_rate = float(r["base_rate"])
            floor = float(r["floor"])
            yes_ask = float(r["yes_ask"]) if r["yes_ask"] else None
            yes_bid = float(r["yes_bid"]) if r["yes_bid"] else None
            if yes_ask is None or yes_bid is None:
                continue
            result = r["result"]
            if result not in ("yes", "no"):
                continue

            inp = ModelInputs(score_now=score, n_now=n_now, base_rate=base_rate,
                              prior_strength=PRIOR_STRENGTH, n_final=nf, drift=DRIFT)
            fair = run_model(inp, n_sims=N_SIMS).prob_at_least(floor) * 100

            edge_yes = fair - yes_ask
            no_ask = 100 - yes_bid
            edge_no = (100 - fair) - no_ask

            if edge_yes >= edge_no:
                direction, edge, cost_c = "YES", edge_yes, yes_ask
                win = (result == "yes")
            else:
                direction, edge, cost_c = "NO", edge_no, no_ask
                win = (result == "no")

            if edge < EDGE_THRESHOLD:
                continue
            if best is None or edge > best[0]:
                best = (edge, {
                    "movie": mk, "floor": floor, "direction": direction,
                    "edge": edge, "fair": fair, "cost_c": cost_c,
                    "win": win, "result": result, "n": n_now,
                    "settle_date": r["settle_date"], "volume": r.get("volume", ""),
                })
        if best:
            trades.append(best[1])

    trades.sort(key=lambda t: t["settle_date"])

    capital = INITIAL_CAPITAL
    equity_curve = [("start", capital)]
    wins = losses = 0
    skipped_no_capital = 0
    total_staked = 0

    for t in trades:
        cost = t["cost_c"] * CONTRACTS / 100
        if cost > capital:
            skipped_no_capital += 1
            continue
        payout = (100 * CONTRACTS / 100) if t["win"] else 0
        pnl = payout - cost
        capital += pnl
        total_staked += cost
        t["pnl"] = pnl
        if t["win"]:
            wins += 1
        else:
            losses += 1
        equity_curve.append((t["settle_date"], round(capital, 2)))

    n_trades = wins + losses
    print("=" * 60)
    print(f"交易笔数: {n_trades}  (胜{wins} 负{losses})")
    if n_trades:
        print(f"胜率: {wins/n_trades*100:.1f}%")
    print(f"初始资金: ${INITIAL_CAPITAL:.2f}")
    print(f"最终资金: ${capital:.2f}")
    print(f"总盈亏: ${capital-INITIAL_CAPITAL:+.2f} "
          f"({(capital/INITIAL_CAPITAL-1)*100:+.1f}%)")
    print(f"总下注额: ${total_staked:.2f}")
    if total_staked:
        print(f"资金回报率(盈亏/下注额): {(capital-INITIAL_CAPITAL)/total_staked*100:+.1f}%")
    if skipped_no_capital:
        print(f"因资金不足跳过: {skipped_no_capital} 笔")
    print("=" * 60)

    peak = INITIAL_CAPITAL
    max_dd = 0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)
    print(f"最大回撤: {max_dd*100:.1f}%")

    print("\n按方向:")
    for d in ["YES", "NO"]:
        dt = [t for t in trades if t.get("direction") == d and "pnl" in t]
        if dt:
            w = sum(1 for t in dt if t["win"])
            print(f"  {d}: {len(dt)}笔, 胜{w}, 盈亏${sum(t['pnl'] for t in dt):+.0f}")

    print("\n按 edge 大小:")
    for lo, hi in [(10, 20), (20, 30), (30, 50), (50, 100)]:
        dt = [t for t in trades if lo <= t["edge"] < hi and "pnl" in t]
        if dt:
            w = sum(1 for t in dt if t["win"])
            print(f"  edge{lo}-{hi}¢: {len(dt)}笔, 胜{w}, 盈亏${sum(t['pnl'] for t in dt):+.0f}")

    print("\n按决策时评论数 n:")
    for lo, hi, name in [(0,20,"<20"),(20,40,"20-40"),(40,80,"40-80"),(80,9999,"80+")]:
        dt = [t for t in trades if lo <= t["n"] < hi and "pnl" in t]
        if dt:
            w = sum(1 for t in dt if t["win"])
            print(f"  n={name}: {len(dt)}笔, 胜{w}, 盈亏${sum(t['pnl'] for t in dt):+.0f}")

    # 大edge明细：验证是否流动性幻觉
    print("\n大edge(≥30¢)交易明细（查是否低成交量/极端门槛=流动性幻觉）:")
    big = [t for t in trades if t["edge"] >= 30 and "pnl" in t]
    for t in sorted(big, key=lambda x: -x["edge"]):
        vol = t.get("volume", "?")
        print(f"  {t['movie'][:22]:22} floor={t['floor']:.0f} {t['direction']} "
              f"edge={t['edge']:.0f}¢ 买价={t['cost_c']:.0f}¢ vol={vol} "
              f"n={t['n']} {'✓' if t['win'] else '✗'} ${t['pnl']:+.0f}")
    low_vol = sum(1 for t in big if str(t.get("volume","")).isdigit() and int(t["volume"])<50)
    if big:
        print(f"  → 大edge里低成交量(vol<50)的: {low_vol}/{len(big)} "
              f"（占多数则说明大edge多为流动性幻觉，实盘吃不到）")

    duration = (datetime.now() - start).total_seconds()
    print(f"\n⏱  耗时: {duration:.0f}秒")

    # 存 JSON + TXT
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = start.strftime("%Y%m%d_%H%M%S")
    tag = "holdout2026" if HOLDOUT_ONLY else "full"

    json_path = os.path.join(RESULTS_DIR, f"pnl_{tag}_{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "scope": scope,
            "params": {"drift": DRIFT, "prior": PRIOR_STRENGTH,
                       "decision_day": DECISION_DAY, "edge_threshold": EDGE_THRESHOLD,
                       "contracts": CONTRACTS, "initial": INITIAL_CAPITAL},
            "n_trades": n_trades, "wins": wins, "losses": losses,
            "final_capital": round(capital, 2),
            "total_pnl": round(capital - INITIAL_CAPITAL, 2),
            "return_on_stake": round((capital-INITIAL_CAPITAL)/total_staked, 4) if total_staked else None,
            "max_drawdown": round(max_dd, 4),
            "equity_curve": equity_curve,
            "trades": [{k: (round(v, 2) if isinstance(v, float) else v)
                        for k, v in t.items()} for t in trades],
        }, f, ensure_ascii=False, indent=2)

    txt_path = os.path.join(RESULTS_DIR, f"pnl_{tag}_{stamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"PnL模拟报告 [{scope}]  {start.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 55 + "\n")
        f.write(f"参数: drift={DRIFT}, prior={PRIOR_STRENGTH}, +{DECISION_DAY}天, "
                f"edge≥{EDGE_THRESHOLD}¢, {CONTRACTS}张/笔\n\n")
        f.write(f"交易{n_trades}笔 (胜{wins} 负{losses})\n")
        if n_trades:
            f.write(f"胜率: {wins/n_trades*100:.1f}%\n")
        f.write(f"初始 ${INITIAL_CAPITAL:.2f} → 最终 ${capital:.2f} "
                f"({(capital/INITIAL_CAPITAL-1)*100:+.1f}%)\n")
        if total_staked:
            f.write(f"资金回报率: {(capital-INITIAL_CAPITAL)/total_staked*100:+.1f}%\n")
        f.write(f"最大回撤: {max_dd*100:.1f}%\n")

    print(f"💾 JSON: {json_path}")
    print(f"💾 TXT: {txt_path}")


if __name__ == "__main__":
    main()