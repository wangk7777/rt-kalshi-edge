"""
第三版 PnL：真实逐档滑点回测。
- 市场价格全部来自 orderbook（orderbooks_merged.json）
- n/score/n_final 从评论数据算（RT）
- 买100张按逐档深度算真实成交均价；深度不足100张则跳过
- 重力策略：n≥80、买NO为主、edge5-10、胜率80-98、排钢镚
- 一片一注、持有到期、固定100张
- 同时输出：理想成交(best price) vs 真实成交(逐档) 对比

用法：py -m scripts.backtest.backtest_pnl_realfill
"""

import json
import os
from datetime import datetime, timezone, timedelta

from src import config
from src.model.bayesian import ModelInputs, run_model

# ---------- 参数----------
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

CONTRACTS = 100
INITIAL_CAPITAL = 1000.0
DIRECTION = "both"          # both / yes_only / no_only
# ---------- n_final 开关 ----------
USE_FIXED_N_FINAL = False     # True=用下面的固定估计值（模拟实盘）; False=用真实n_final（回测上帝视角）
FIXED_N_FINAL = 400         # USE_FIXED_N_FINAL=True 时，所有片统一用这个估计值
# ---------- 避开压线门槛 ----------
AVOID_BOUNDARY = False       # True=跳过预测最终分接近门槛的合约
BOUNDARY_MARGIN = 1         # 预测最终分距门槛±此值内视为压线，跳过


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
    """结算时刻(14:00 UTC)前的累计评论数。"""
    return sum(1 for r in reviews
               if parse_dt(r.get("date")) and parse_dt(r["date"]) <= settle_dt)


def score_n_at(reviews_sorted, cutoff_dt):
    """截至 cutoff_dt 的 (score, n)。score=fresh比例*100。"""
    fresh = 0
    n = 0
    for dt, fr in reviews_sorted:
        if dt <= cutoff_dt:
            n += 1
            if fr:
                fresh += 1
        else:
            break
    if n == 0:
        return None, 0
    return round(fresh / n * 100), n


# ---------- 逐档吃单（滑点核心）----------
def fill_yes(yes_asks, qty):
    """买YES qty张，从best_ask逐档吃。返回成交均价¢或None(深度不足)。"""
    need, cost = qty, 0.0
    for price, size in yes_asks:
        take = min(need, float(size))
        cost += take * float(price)
        need -= take
        if need <= 0:
            break
    return (cost / qty) if need <= 0 else None


def fill_no(yes_bids, qty):
    """买NO qty张=卖YES，从best_bid(降序)逐档吃。返回NO成本¢或None。"""
    need, proceeds = qty, 0.0
    for price, size in yes_bids:
        take = min(need, float(size))
        proceeds += take * float(price)
        need -= take
        if need <= 0:
            break
    return (100 - proceeds / qty) if need <= 0 else None


# ---------- 主流程 ----------
def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ob_data = json.load(open(OB_PATH, encoding="utf-8"))
    print(f"📂 加载 orderbook: {len(ob_data)} 部电影\n")

    model_cache = {}
    n_final_this = [0]  # 用list绕过闭包

    def model_result(score, n, base_rate):
        """返回模型结果对象（含mean和prob_at_least），按(score,n,base_rate)缓存。"""
        key = (score, n, base_rate)
        if key in model_cache:
            return model_cache[key]
        nf = FIXED_N_FINAL if USE_FIXED_N_FINAL else n_final_this[0]
        inp = ModelInputs(score_now=score, n_now=n, base_rate=base_rate,
                          prior_strength=PRIOR_STRENGTH,
                          n_final=max(nf, n), drift=DRIFT)
        res = run_model(inp, n_sims=N_SIMS)
        model_cache[key] = res
        return res

    trades = []
    skipped_depth = 0   # 因深度不足跳过的候选数

    for movie_key, mdata in ob_data.items():
        m_cfg = config.WATCHLIST.get(movie_key, {})
        base_rate = m_cfg.get("base_rate")
        if base_rate is None:
            continue
        base_rate = float(base_rate)

        reviews = load_reviews(movie_key)
        if not reviews:
            print(f"  ⚠ {movie_key} 无评论文件，跳过")
            continue
        reviews_sorted = sorted(
            [(parse_dt(r.get("date")), is_fresh(r)) for r in reviews if parse_dt(r.get("date"))],
            key=lambda x: x[0])

        settle_dt = parse_dt(mdata.get("settle_date", "") + "T14:00:00Z") \
            if "T" not in str(mdata.get("settle_date", "")) else parse_dt(mdata.get("settle_date"))
        if settle_dt is None:
            continue
        if not USE_FIXED_N_FINAL:
            n_final_this[0] = compute_n_final(reviews, settle_dt)

        # 收集该片所有(小时, 门槛)的候选，按时间排序，选第一个满足的下注（一片一注）
        markets = mdata.get("markets", {})
        # 把所有门槛的所有小时快照，按时间戳汇总
        hourly_points = []  # (ts, hour_key, ticker, floor, result, snap)
        for ticker, mk in markets.items():
            floor = mk.get("floor")
            result = mk.get("result")
            for hk, snap in mk.get("hourly_snapshots", {}).items():
                hourly_points.append((snap["ts"], hk, ticker, floor, result, snap))
        hourly_points.sort(key=lambda x: x[0])

        bet_placed = False
        for ts, hk, ticker, floor, result, snap in hourly_points:
            if bet_placed:
                break
            if floor is None or result not in ("yes", "no"):
                continue

            cutoff_dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            score, n = score_n_at(reviews_sorted, cutoff_dt)
            if score is None or n < N_MIN:
                continue

            # orderbook 的 best bid/ask
            try:
                yes_bid = float(snap["best_bid"])
                yes_ask = float(snap["best_ask"])
            except (TypeError, ValueError, KeyError):
                continue
            yes_bids = snap.get("yes_bids", [])
            yes_asks = snap.get("yes_asks", [])

            # 真实盘口价差过滤：价差太大说明市场不活跃/不确定，实际难成交
            if yes_ask - yes_bid > SPREAD_MAX:
                continue

            res = model_result(score, n, base_rate)
            predicted_final = res.mean          # 预测最终分
            # 避开压线门槛：预测最终分距门槛太近则跳过
            if AVOID_BOUNDARY and abs(predicted_final - floor) <= BOUNDARY_MARGIN:
                continue
            prob_yes = res.prob_at_least(floor + 1)
            prob_no = 1 - prob_yes

            no_ask = 100 - yes_bid
            edge_yes = prob_yes * 100 - yes_ask
            edge_no = prob_no * 100 - no_ask

            candidate = None

            if DIRECTION in ("both", "yes_only") and \
               WIN_PROB_MIN <= prob_yes <= WIN_PROB_MAX and \
               EDGE_MIN <= edge_yes <= EDGE_MAX and yes_ask < PRICE_MAX:
                real = fill_yes(yes_asks, CONTRACTS)
                if real is None:
                    skipped_depth += 1
                else:
                    candidate = {
                        "direction": "YES", "ideal_cost": yes_ask, "real_cost": real,
                        "won": result == "yes", "edge": edge_yes, "win_prob": prob_yes,
                    }

            if candidate is None and DIRECTION in ("both", "no_only") and \
               WIN_PROB_MIN <= prob_no <= WIN_PROB_MAX and \
               EDGE_MIN <= edge_no <= EDGE_MAX and no_ask < PRICE_MAX:
                real = fill_no(yes_bids, CONTRACTS)
                if real is None:
                    skipped_depth += 1
                else:
                    candidate = {
                        "direction": "NO", "ideal_cost": no_ask, "real_cost": real,
                        "won": result == "no", "edge": edge_no, "win_prob": prob_no,
                    }

            if candidate:
                candidate.update({
                    "movie": movie_key, "time": hk, "floor": floor, "ticker": ticker,
                    "n": n, "score": score, "final_score": mdata.get("final_score"),
                    "predicted_final": predicted_final,
                    "settle_date": mdata.get("settle_date"),
                    "yes_bid": yes_bid, "yes_ask": yes_ask,
                })
                trades.append(candidate)
                bet_placed = True

    # ---------- 结算（只算真实成交）----------
    def settle_real(subset):
        cap = INITIAL_CAPITAL
        wins = 0
        pnl_total = 0.0
        detail = []
        for t in sorted(subset, key=lambda x: x["settle_date"]):
            cost = t["real_cost"]
            pnl = (100 - cost) * CONTRACTS / 100.0 if t["won"] else -cost * CONTRACTS / 100.0
            pnl_total += pnl
            cap += pnl
            if t["won"]:
                wins += 1
            detail.append((t, pnl))
        return cap, wins, pnl_total, detail

    real_cap, real_wins, real_pnl, real_detail = settle_real(trades)
    n_trades = len(trades)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(RESULTS_DIR, f"report_realfill_{stamp}.txt")
    import sys
    class Tee:
        def __init__(self, *fs): self.fs = fs
        def write(self, t):
            for f in self.fs: f.write(t)
        def flush(self):
            for f in self.fs: f.flush()
    rf = open(report_path, "w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, rf)

    print(f"🕐 PnL第三版(真实逐档滑点) {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"参数: drift={DRIFT} prior={PRIOR_STRENGTH} n≥{N_MIN} "
          f"胜率≥{WIN_PROB_MIN:.0%} 胜率≤{WIN_PROB_MAX:.0%} 买价<{PRICE_MAX}¢ "
          f"edge≥{EDGE_MIN} edge≤{EDGE_MAX} 价差≤{SPREAD_MAX} {DIRECTION} {CONTRACTS}张 ${INITIAL_CAPITAL:.0f}")
    nf_mode = f"固定n_final={FIXED_N_FINAL}(模拟实盘)" if USE_FIXED_N_FINAL else "真实n_final(回测)"
    print(f"n_final模式: {nf_mode}")
    print(f"市场价来源: orderbook逐档 | n/score: 评论切片\n")

    if n_trades == 0:
        print("无交易。")
        sys.stdout = orig; rf.close()
        return

    print("=" * 60)
    print(f"[真实滑点] 交易 {n_trades} 笔 (胜{real_wins} 负{n_trades-real_wins})  "
          f"因深度不足跳过 {skipped_depth} 个候选")
    print(f"胜率: {real_wins/n_trades*100:.1f}%")
    print(f"初始 ${INITIAL_CAPITAL:.2f} → 最终 ${real_cap:.2f} "
          f"({(real_cap/INITIAL_CAPITAL-1)*100:+.1f}%)")
    print(f"回报率(盈亏/下注): {real_pnl/(n_trades*CONTRACTS)*100:+.1f}%")
    avg_slip = sum(t["real_cost"]-t["ideal_cost"] for t in trades)/n_trades
    print(f"平均每笔滑点: {avg_slip:+.2f}¢")
    print("=" * 60)

    print("\n按方向:")
    for d in ("YES", "NO"):
        dt = [t for t in trades if t["direction"] == d]
        if dt:
            dwins = sum(1 for t in dt if t["won"])
            _, _, dpnl, _ = settle_real(dt)
            print(f"  {d}: {len(dt)}笔 胜{dwins} 盈亏${dpnl:+.0f}")

    print("\n按胜率区间:")
    lo = WIN_PROB_MIN
    while lo < WIN_PROB_MAX - 1e-9:
        hi = min(round(lo + 0.05, 2), WIN_PROB_MAX)
        grp = [t for t in trades if (lo <= t["win_prob"] < hi) or
               (hi >= WIN_PROB_MAX - 1e-9 and lo <= t["win_prob"] <= hi)]
        if grp:
            gw = sum(1 for t in grp if t["won"])
            _, _, gpnl, _ = settle_real(grp)
            print(f"  胜率{lo:.0%}-{hi:.0%}: {len(grp)}笔 实际胜{gw}/{len(grp)} 盈亏${gpnl:+.0f}")
        lo = hi

    print("\n按 edge 大小:")
    for elo, ehi in [(5, 10), (10, 20), (20, 100)]:
        grp = [t for t in trades if elo <= t["edge"] < ehi]
        if grp:
            gw = sum(1 for t in grp if t["won"])
            _, _, gpnl, _ = settle_real(grp)
            print(f"  edge{elo}-{ehi}¢: {len(grp)}笔 胜{gw} 盈亏${gpnl:+.0f}")

    # ---------- 新增：按月份统计 ----------
    print("\n按月份:")
    from collections import defaultdict
    month_groups = defaultdict(lambda: {"n": 0, "win": 0, "pnl": 0.0})

    for t, pnl in real_detail:
        month = str(t["settle_date"])[:7]
        g = month_groups[month]
        g["n"] += 1
        g["pnl"] += pnl
        if t["won"]:
            g["win"] += 1
    for month in sorted(month_groups):
        g = month_groups[month]
        print(f"  {month}: {g['n']}笔 胜{g['win']}/{g['n']} 盈亏${g['pnl']:+.0f}")

    print("\n前20笔交易明细:")
    for t, pnl in real_detail[:20]:
        mark = "✓" if t["won"] else "✗"
        print(f"  {t['movie'][:20]:20} {t['time']} floor={t['floor']:.0f} "
              f"{t['direction']} 胜率{t['win_prob']:.0%} edge{t['edge']:.0f}¢ "
              f"真实{t['real_cost']:.1f}¢ n={t['n']} {mark} ${pnl:+.0f}")

    sys.stdout = orig
    rf.close()
    print(f"\n💾 报告: {report_path}")

    # ---------- CSV（保留真实滑点信息，删理想只留真实成交价）----------
    import csv
    csv_path = os.path.join(RESULTS_DIR, f"trades_realfill_{stamp}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["电影", "时刻", "门槛", "方向", "模型胜率", "edge",
                    "真实买价", "滑点", "价差", "决策n", "score", "预测最终分",
                    "最终分", "yes_bid", "yes_ask", "是否赢", "真实盈亏", "settle"])
        for t, pnl in real_detail:
            w.writerow([
                t["movie"], t["time"], f"{t['floor']:.0f}", t["direction"],
                f"{t['win_prob']:.3f}", f"{t['edge']:.1f}",
                f"{t['real_cost']:.2f}",
                f"{t['real_cost']-t['ideal_cost']:+.2f}",
                f"{t['yes_ask']-t['yes_bid']:.0f}",
                t["n"], t["score"], f"{t['predicted_final']:.1f}", t.get("final_score", ""),
                f"{t['yes_bid']:.0f}", f"{t['yes_ask']:.0f}",
                "赢" if t["won"] else "输", f"{pnl:+.0f}", t["settle_date"],
            ])
    print(f"💾 CSV: {csv_path}")


def settle_pnl_subset(subset, cost_field):
    cap = INITIAL_CAPITAL
    wins = 0
    pnl_total = 0.0
    for t in subset:
        cost = t[cost_field]
        pnl = (100 - cost) * CONTRACTS / 100.0 if t["won"] else -cost * CONTRACTS / 100.0
        pnl_total += pnl
        cap += pnl
        if t["won"]:
            wins += 1
    return cap, wins, pnl_total, None


if __name__ == "__main__":
    main()