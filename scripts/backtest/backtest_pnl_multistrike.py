"""
第四版 PnL：多门槛 + 仓位管理（真实逐档滑点）。

相比第三版的变化：
- 多门槛：同一floor只买一次，但同片不同floor可各买一次（不再一片一注）
- 仓位管理：每笔买入量 = min(本金比例允许, 深度滑点≤2¢允许, 绝对上限)
- 资金滚动：本金随盈亏变化，后续下注跟着变
- 同时机会：按时间先到先得，本金不足则跳过（记录）
- 详细报告：每片买了几个门槛/集中度、资金不足跳过、约束来源、回撤、按月

用法：py -m scripts.backtest.backtest_pnl_multistrike
"""

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from src import config
from src.model.bayesian import ModelInputs, run_model

# ---------- 策略参数（沿用重力策略）----------
_p = config.get_strategy_params()   # 纯默认
DRIFT = _p["DRIFT"]
PRIOR_STRENGTH = _p["PRIOR_STRENGTH"]
N_MIN = _p["N_MIN"]
WIN_PROB_MIN = _p["WIN_PROB_MIN"]
WIN_PROB_MAX = _p["WIN_PROB_MAX"]
PRICE_MAX = _p["PRICE_MAX"]
EDGE_MIN = _p["EDGE_MIN"]
EDGE_MAX = _p["EDGE_MAX"]
SPREAD_MAX = _p["SPREAD_MAX"]
N_SIMS = _p["N_SIMS"]

DIRECTION = "both"              # both / yes_only / no_only

# ---------- 仓位管理参数（跑前可调）----------
MAX_STRIKES_PER_MOVIE = 99      # 每部电影最多买几个门槛（99=不限）
RISK_PCT = 0.10                # 每笔最多押本金的比例
MAX_SLIPPAGE_CENT = 2.0        # 深度约束：吃到均价滑点≤此值
MAX_CONTRACTS_PER_TRADE = 300  # 每笔绝对上限（保险丝）
MAX_MOVIE_EXPOSURE_PCT = 1.0  # 单片所有门槛总仓位≤本金比例（1.0=不限）
MIN_CONTRACTS = 10             # 低于此量不值得下

INITIAL_CAPITAL = 3000.0

OB_PATH = os.path.join("data", "backtest", "orderbooks_merged.json")
HISTORICAL_DIR = os.path.join("data", "historical")
RESULTS_DIR = os.path.join("data", "backtest", "results", "pnl")


# ---------- 工具 ----------
def parse_dt(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def is_fresh(r):
    s = str(r.get("sentiment", ""))
    return "Fresh" in s or s.upper() == "POSITIVE"


def load_reviews(movie_key):
    p = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def compute_n_final(reviews, settle_dt):
    return sum(1 for r in reviews
               if parse_dt(r.get("date")) and parse_dt(r["date"]) <= settle_dt)


def score_n_at(reviews_sorted, cutoff_dt):
    fresh = n = 0
    for dt, fr in reviews_sorted:
        if dt <= cutoff_dt:
            n += 1
            if fr:
                fresh += 1
        else:
            break
    if n == 0:
        return None, 0
    return round(fresh / n * 100, 2), n


# ---------- 深度与滑点 ----------
def depth_limited_qty(levels, max_slip):
    """逐档吃，返回滑点≤max_slip的最大张数。"""
    if not levels:
        return 0
    best = float(levels[0][0])
    cum_cost = 0.0
    cum_qty = 0
    allowed = 0
    for price, size in levels:
        p = float(price)
        s = float(size)
        test_qty = cum_qty + s
        test_cost = cum_cost + p * s
        if test_qty > 0 and abs(test_cost / test_qty - best) <= max_slip:
            cum_qty = test_qty
            cum_cost = test_cost
            allowed = int(cum_qty)
        else:
            denom = p - (best + max_slip)
            if denom < 0:
                x = int(((best + max_slip) * cum_qty - cum_cost) / denom)
                allowed = cum_qty + max(0, x)
            break
    return allowed


def fill_avg(levels, qty):
    """吃qty张的成交均价（假设qty≤深度）。"""
    need = qty
    cost = 0.0
    for price, size in levels:
        take = min(need, float(size))
        cost += take * float(price)
        need -= take
        if need <= 0:
            break
    return cost / qty if qty > 0 and need <= 0 else None


def decide_qty(levels, capital, is_no):
    """三约束取min。返回 (qty, real_cost_cent, 约束来源) 或 (0,None,原因)。"""
    depth_max = depth_limited_qty(levels, MAX_SLIPPAGE_CENT)
    if depth_max < MIN_CONTRACTS:
        return 0, None, "深度不足"
    avg_yes = fill_avg(levels, min(depth_max, MAX_CONTRACTS_PER_TRADE))
    if avg_yes is None:
        return 0, None, "深度不足"
    unit_cost = (100 - avg_yes) if is_no else avg_yes    # ¢/张
    if unit_cost <= 0:
        return 0, None, "价格异常"
    budget_dollars = capital * RISK_PCT
    budget_max = int(budget_dollars * 100 / unit_cost)   # $→¢→张
    qty = min(depth_max, budget_max, MAX_CONTRACTS_PER_TRADE)
    if qty < MIN_CONTRACTS:
        return 0, None, "本金不足"
    src = min([(depth_max, "深度"), (budget_max, "本金"),
               (MAX_CONTRACTS_PER_TRADE, "上限")], key=lambda x: x[0])[1]
    real_avg = fill_avg(levels, qty)
    real_cost = (100 - real_avg) if is_no else real_avg
    return qty, real_cost, src


# ---------- 主流程 ----------
def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ob_data = json.load(open(OB_PATH, encoding="utf-8"))

    model_cache = {}
    n_final_this = [0]

    def model_prob(score, n, base_rate, floor):
        key = (score, n, base_rate, floor)
        if key in model_cache:
            return model_cache[key]
        inp = ModelInputs(score_now=score, n_now=n, base_rate=base_rate,
                          prior_strength=PRIOR_STRENGTH,
                          n_final=max(n_final_this[0], n), drift=DRIFT)
        p = run_model(inp, n_sims=N_SIMS).prob_at_least(floor + 1)
        model_cache[key] = p
        return p

    # 第一遍：收集所有可交易机会（跨片、跨门槛、跨时刻），带时间戳
    # 每个(movie,floor)只取"第一个满足条件"的时刻
    opportunities = []   # dict: movie, floor, ticker, direction, edge, win_prob, ts, time, levels, result, n, score, final_score, settle
    for movie_key, mdata in ob_data.items():
        m_cfg = config.WATCHLIST.get(movie_key, {})
        base_rate = m_cfg.get("base_rate")
        if base_rate is None:
            continue
        base_rate = float(base_rate)

        reviews = load_reviews(movie_key)
        if not reviews:
            continue
        reviews_sorted = sorted(
            [(parse_dt(r.get("date")), is_fresh(r)) for r in reviews if parse_dt(r.get("date"))],
            key=lambda x: x[0])

        settle_raw = mdata.get("settle_date", "")
        settle_dt = parse_dt(settle_raw if "T" in str(settle_raw) else settle_raw + "T14:00:00Z")
        if settle_dt is None:
            continue
        n_final_this[0] = compute_n_final(reviews, settle_dt)

        for ticker, mk in mdata.get("markets", {}).items():
            floor = mk.get("floor")
            result = mk.get("result")
            if floor is None or result not in ("yes", "no"):
                continue
            # 该门槛：按时间找第一个满足条件的时刻
            snaps = sorted(mk.get("hourly_snapshots", {}).items(),
                           key=lambda x: x[1]["ts"])
            for hk, snap in snaps:
                ts = snap["ts"]
                cutoff_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                score, n = score_n_at(reviews_sorted, cutoff_dt)
                if score is None or n < N_MIN:
                    continue
                try:
                    yes_bid = float(snap["best_bid"])
                    yes_ask = float(snap["best_ask"])
                except (TypeError, ValueError, KeyError):
                    continue
                if yes_ask - yes_bid > SPREAD_MAX:
                    continue
                prob_yes = model_prob(score, n, base_rate, floor)
                prob_no = 1 - prob_yes
                no_ask = 100 - yes_bid
                edge_yes = prob_yes * 100 - yes_ask
                edge_no = prob_no * 100 - no_ask

                chosen = None
                if DIRECTION in ("both", "yes_only") and \
                   WIN_PROB_MIN <= prob_yes <= WIN_PROB_MAX and \
                   EDGE_MIN <= edge_yes <= EDGE_MAX and yes_ask < PRICE_MAX:
                    chosen = ("YES", edge_yes, prob_yes, snap.get("yes_asks", []), result == "yes")
                elif DIRECTION in ("both", "no_only") and \
                     WIN_PROB_MIN <= prob_no <= WIN_PROB_MAX and \
                     EDGE_MIN <= edge_no <= EDGE_MAX and no_ask < PRICE_MAX:
                    chosen = ("NO", edge_no, prob_no, snap.get("yes_bids", []), result == "no")

                if chosen:
                    direction, edge, win_prob, levels, won = chosen
                    opportunities.append({
                        "movie": movie_key, "floor": floor, "ticker": ticker,
                        "direction": direction, "edge": edge, "win_prob": win_prob,
                        "levels": levels, "won": won, "ts": ts, "time": hk,
                        "n": n, "score": score, "final_score": mdata.get("final_score"),
                        "settle_date": settle_raw, "is_no": direction == "NO",
                    })
                    break   # 该门槛只取第一个满足时刻

    # 第二遍：按时间先到先得，资金滚动下注
    opportunities.sort(key=lambda x: x["ts"])
    capital = INITIAL_CAPITAL
    open_positions = []   # 未结算持仓：{settle_ts, cost, qty, won, ...}
    trades = []
    skipped = {"本金不足": [], "深度不足": [], "门槛上限": [], "价格异常": [], "单片上限": []}
    strikes_per_movie = defaultdict(int)
    movie_exposure = defaultdict(float)   # 每片当前已投入金额（$）

    # 为结算：把settle时间转成ts
    def settle_ts_of(op):
        sd = parse_dt(op["settle_date"] if "T" in str(op["settle_date"])
                      else op["settle_date"] + "T14:00:00Z")
        return sd.timestamp() * 1000 if sd else float("inf")

    for op in opportunities:
        now_ts = op["ts"]
        # 先结算所有到期的持仓（settle <= now），释放资金
        still_open = []
        for pos in open_positions:
            if pos["settle_ts"] <= now_ts:
                payoff = (100 * pos["qty"] / 100.0) if pos["won"] else 0.0
                capital += payoff   # 赢：每张结算$1；输：$0（成本已在买入时扣）
            else:
                still_open.append(pos)
        open_positions = still_open

        # 每片门槛数上限
        if strikes_per_movie[op["movie"]] >= MAX_STRIKES_PER_MOVIE:
            skipped["门槛上限"].append(op)
            continue

        # 决定下注量（三约束）
        qty, real_cost, src = decide_qty(op["levels"], capital, op["is_no"])
        if qty == 0:
            reason = src if src in skipped else "本金不足"
            skipped.setdefault(reason, []).append(op)
            continue

        # 单片总仓位上限：本片已投入 + 这笔 ≤ 本金 × MAX_MOVIE_EXPOSURE_PCT
        movie_budget = capital * MAX_MOVIE_EXPOSURE_PCT
        remaining_movie_budget = movie_budget - movie_exposure[op["movie"]]
        this_cost = real_cost * qty / 100.0
        if this_cost > remaining_movie_budget:
            max_qty_by_movie = int(remaining_movie_budget * 100 / real_cost) if real_cost > 0 else 0
            if max_qty_by_movie < MIN_CONTRACTS:
                skipped["单片上限"].append(op)
                continue
            qty = max_qty_by_movie
            src = "单片上限"
            real_cost_new = fill_avg(op["levels"], qty)
            if real_cost_new is not None:
                real_cost = (100 - real_cost_new) if op["is_no"] else real_cost_new

        # 扣资金（买入成本）
        cost_dollars = real_cost * qty / 100.0
        if cost_dollars > capital:
            skipped["本金不足"].append(op)
            continue
        capital -= cost_dollars
        movie_exposure[op["movie"]] += cost_dollars   # 累加单片已投入

        strikes_per_movie[op["movie"]] += 1
        st_ts = settle_ts_of(op)
        pos = {
            "settle_ts": st_ts, "qty": qty, "won": op["won"],
            "cost_cent": real_cost, "cost_dollars": cost_dollars,
        }
        open_positions.append(pos)

        # 记录交易
        pnl = (100 - real_cost) * qty / 100.0 if op["won"] else -real_cost * qty / 100.0
        trades.append({**op, "qty": qty, "real_cost": real_cost,
                       "constraint": src, "pnl": pnl,
                       "capital_after": None})   # capital_after结算后才准，这里先占位

    # 结算所有剩余持仓
    for pos in open_positions:
        if pos["won"]:
            capital += 100 * pos["qty"] / 100.0

    # ---------- 资金曲线 + 最大回撤（按结算时间）----------
    settled_seq = sorted(trades, key=lambda x: (str(x["settle_date"]), x["ts"]))
    cap_track = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_dd = 0.0
    max_dd_date = None
    for t in settled_seq:
        cap_track += t["pnl"]
        if cap_track > peak:
            peak = cap_track
        dd = (peak - cap_track) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_date = t["settle_date"]

    # ---------- 报告 ----------
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(RESULTS_DIR, f"report_multistrike_{stamp}.txt")

    class Tee:
        def __init__(self, *fs): self.fs = fs
        def write(self, t):
            for f in self.fs: f.write(t)
        def flush(self):
            for f in self.fs: f.flush()

    rf = open(report_path, "w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, rf)

    n_trades = len(trades)
    wins = sum(1 for t in trades if t["won"])
    total_pnl = sum(t["pnl"] for t in trades)
    total_staked = sum(t["real_cost"] * t["qty"] / 100.0 for t in trades)

    print(f"🕐 PnL第四版(多门槛+仓位管理) {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"策略参数: drift={DRIFT} prior={PRIOR_STRENGTH} n≥{N_MIN} "
          f"胜率{WIN_PROB_MIN:.0%}-{WIN_PROB_MAX:.0%} 买价<{PRICE_MAX}¢ "
          f"edge{EDGE_MIN}-{EDGE_MAX} 价差≤{SPREAD_MAX} {DIRECTION}")
    print(f"仓位参数: 每片≤{MAX_STRIKES_PER_MOVIE}门槛 风险{RISK_PCT:.0%}/笔 "
          f"滑点≤{MAX_SLIPPAGE_CENT}¢ 上限{MAX_CONTRACTS_PER_TRADE}张 "
          f"单片上限{MAX_MOVIE_EXPOSURE_PCT:.0%} 最小{MIN_CONTRACTS}张")
    print(f"市场价: orderbook逐档 | n/score: 评论切片\n")

    if n_trades == 0:
        print("无交易。")
        sys.stdout = orig
        rf.close()
        return

    print("=" * 64)
    print(f"[多门槛] 交易 {n_trades} 笔 (胜{wins} 负{n_trades-wins}) 胜率{wins/n_trades*100:.1f}%")
    print(f"初始 ${INITIAL_CAPITAL:.2f} → 最终 ${capital:.2f} "
          f"({(capital/INITIAL_CAPITAL-1)*100:+.1f}%)")
    print(f"总下注额 ${total_staked:.0f}  总盈亏 ${total_pnl:+.0f}  "
          f"回报率(盈亏/下注) {total_pnl/total_staked*100:+.1f}%")
    print(f"平均下注量 {sum(t['qty'] for t in trades)/n_trades:.0f}张 "
          f"(最小{min(t['qty'] for t in trades)} 最大{max(t['qty'] for t in trades)})")
    if max_dd > 0:
        print(f"最大回撤: {max_dd*100:.1f}% (发生在 {max_dd_date} 前后)")
    else:
        print(f"最大回撤: 0%（全程无回撤，本金单调上升）")
    print("=" * 64)

    # 按方向
    print("\n按方向:")
    for d in ("YES", "NO"):
        dt = [t for t in trades if t["direction"] == d]
        if dt:
            dw = sum(1 for t in dt if t["won"])
            print(f"  {d}: {len(dt)}笔 胜{dw} 盈亏${sum(t['pnl'] for t in dt):+.0f} "
                  f"下注${sum(t['real_cost']*t['qty']/100 for t in dt):.0f}")

    # 按胜率区间
    print("\n按胜率区间:")
    lo = WIN_PROB_MIN
    while lo < WIN_PROB_MAX - 1e-9:
        hi = min(round(lo + 0.05, 2), WIN_PROB_MAX)
        grp = [t for t in trades if (lo <= t["win_prob"] < hi) or
               (hi >= WIN_PROB_MAX - 1e-9 and lo <= t["win_prob"] <= hi)]
        if grp:
            gw = sum(1 for t in grp if t["won"])
            print(f"  胜率{lo:.0%}-{hi:.0%}: {len(grp)}笔 胜{gw}/{len(grp)} "
                  f"盈亏${sum(t['pnl'] for t in grp):+.0f}")
        lo = hi

    # 按edge
    print("\n按edge大小:")
    for elo, ehi in [(5, 10), (10, 20), (20, 100)]:
        grp = [t for t in trades if elo <= t["edge"] < ehi]
        if grp:
            gw = sum(1 for t in grp if t["won"])
            print(f"  edge{elo}-{ehi}¢: {len(grp)}笔 胜{gw} 盈亏${sum(t['pnl'] for t in grp):+.0f}")

    # 按约束来源
    print("\n下注量约束来源:")
    csrc = defaultdict(lambda: [0, 0.0])
    for t in trades:
        csrc[t["constraint"]][0] += 1
        csrc[t["constraint"]][1] += t["qty"]
    for src, (cnt, qsum) in csrc.items():
        print(f"  {src}: {cnt}笔 (平均{qsum/cnt:.0f}张)")

    # 按月份（增强：月回报率、月末本金、最大单笔盈亏）
    print("\n按月份:")
    mg = defaultdict(lambda: {"n": 0, "win": 0, "pnl": 0.0, "stake": 0.0,
                              "max_win": 0.0, "max_loss": 0.0})
    for t in trades:
        mo = str(t["settle_date"])[:7]
        g = mg[mo]
        g["n"] += 1
        g["pnl"] += t["pnl"]
        g["stake"] += t["real_cost"] * t["qty"] / 100.0
        if t["won"]:
            g["win"] += 1
        g["max_win"] = max(g["max_win"], t["pnl"])
        g["max_loss"] = min(g["max_loss"], t["pnl"])
    # 月末本金（按settle累积）
    running_cap = INITIAL_CAPITAL
    month_end_cap = {}
    for t in sorted(trades, key=lambda x: str(x["settle_date"])):
        running_cap += t["pnl"]
        month_end_cap[str(t["settle_date"])[:7]] = running_cap

    print(f"  {'月份':8}{'笔':>4}{'胜率':>6}{'盈亏':>8}{'下注':>7}"
          f"{'月回报':>8}{'月末本金':>9}   最大盈/亏")
    prev_cap = INITIAL_CAPITAL
    for mo in sorted(mg):
        g = mg[mo]
        end_cap = month_end_cap[mo]
        month_ret = g["pnl"] / prev_cap * 100 if prev_cap > 0 else 0
        print(f"  {mo:8}{g['n']:>4}{g['win']/g['n']*100:>5.0f}%"
              f"${g['pnl']:>+6.0f}${g['stake']:>5.0f}"
              f"{month_ret:>+7.1f}%${end_cap:>7.0f}"
              f"   +{g['max_win']:.0f}/{g['max_loss']:.0f}")
        prev_cap = end_cap

    # 单片集中度
    print("\n单片集中度(买了多个门槛的电影):")
    movie_trades = defaultdict(list)
    for t in trades:
        movie_trades[t["movie"]].append(t)
    multi = {m: ts for m, ts in movie_trades.items() if len(ts) > 1}
    for m, ts in sorted(multi.items(), key=lambda x: -len(x[1])):
        floors = sorted(int(t["floor"]) for t in ts)
        w = sum(1 for t in ts if t["won"])
        pnl = sum(t["pnl"] for t in ts)
        allw = "全赢" if w == len(ts) else ("全输" if w == 0 else f"{w}赢{len(ts)-w}输")
        print(f"  {m[:26]:28} {len(ts)}门槛{floors} {allw} 盈亏${pnl:+.0f}")
    if not multi:
        print("  （无电影买入多个门槛）")

    # 资金不足/跳过统计
    print("\n跳过的机会:")
    for reason, ops in skipped.items():
        if ops:
            print(f"  {reason}: {len(ops)}个")
            for op in ops[:5]:
                print(f"      {op['movie'][:24]:26} floor={op['floor']:.0f} "
                      f"{op['direction']} {op['time']}")
            if len(ops) > 5:
                print(f"      ...还有{len(ops)-5}个")

    # 前20笔明细
    print("\n前20笔交易明细:")
    for t in sorted(trades, key=lambda x: x["ts"])[:20]:
        mark = "✓" if t["won"] else "✗"
        print(f"  {t['movie'][:18]:18} {t['time']} floor={t['floor']:.0f} "
              f"{t['direction']} 胜率{t['win_prob']:.0%} edge{t['edge']:.0f}¢ "
              f"{t['qty']}张@{t['real_cost']:.1f}¢({t['constraint']}) "
              f"n={t['n']} {mark} ${t['pnl']:+.0f}")

    sys.stdout = orig
    rf.close()
    print(f"\n💾 报告: {report_path}")

    # CSV
    csv_path = os.path.join(RESULTS_DIR, f"trades_multistrike_{stamp}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["电影", "时刻", "门槛", "方向", "模型胜率", "edge",
                    "下注量", "真实买价", "约束来源", "决策n", "score",
                    "最终分", "是否赢", "盈亏", "settle"])
        for t in sorted(trades, key=lambda x: x["ts"]):
            w.writerow([
                t["movie"], t["time"], f"{t['floor']:.0f}", t["direction"],
                f"{t['win_prob']:.3f}", f"{t['edge']:.1f}", t["qty"],
                f"{t['real_cost']:.2f}", t["constraint"], t["n"], t["score"],
                t.get("final_score", ""), "赢" if t["won"] else "输",
                f"{t['pnl']:+.0f}", t["settle_date"],
            ])
    print(f"💾 CSV: {csv_path}")


if __name__ == "__main__":
    main()