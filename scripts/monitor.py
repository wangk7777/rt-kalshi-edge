"""
盯盘脚本（第一版）：实时监控当前上映电影，发现符合重力策略的交易机会，打印通知。

数据源：
- RT 实时分数/评论数：src.collectors.rt_summary
- Kalshi 门槛列表+best价：src.collectors.kalshi_client.get_ladder_live
- Kalshi 逐档深度：src.collectors.kalshi_client.fetch_market_orderbook
- 模型：src.model.bayesian

盯盘范围：watchlist 里 lift_date <= 今天 < settle_date 的片（自动筛，零维护）。
每 15 分钟循环一次。同一(电影,门槛)通知一次后不再重复。
Ctrl+C 停止。

用法：py -m scripts.monitor
"""

import time
import sys
from datetime import datetime, timezone

from src import config
from src.collectors import kalshi_client as kc
from src.collectors.rt_summary import fetch_summary_safe
from src.model.bayesian import ModelInputs, run_model

# ================= 策略参数（随时改）=================
DRIFT = 0.0
PRIOR_STRENGTH = 20.0
N_SIMS = 50_000
N_MIN = 80
WIN_PROB_MIN = 0.80
WIN_PROB_MAX = 0.92
PRICE_MAX = 90            # 买价上限¢
EDGE_MIN = 5
EDGE_MAX = 10
SPREAD_MAX = 5
FIXED_N_FINAL = 200       # 实盘用固定估计值
CONTRACTS = 100           # 检查深度是否够买这么多
DIRECTION = "both"        # both / yes_only / no_only

INTERVAL_MINUTES = 15     # 循环间隔
# ====================================================


def parse_dt(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def get_watching_movies():
    """从 watchlist 筛出当前该盯的片：lift_date <= 今天 < settle_date。"""
    today = datetime.now(timezone.utc)
    watching = []
    for k, m in config.WATCHLIST.items():
        settle = m.get("kalshi_settle_date", "")
        settle_dt = parse_dt(settle if "T" in str(settle) else settle + "T14:00:00Z")
        lift = m.get("lift_date") or m.get("embargo_date")
        lift_dt = parse_dt(str(lift) + "T00:00:00Z") if lift else None
        if settle_dt is None:
            continue
        # 还没结算
        if today >= settle_dt:
            continue
        # 已解禁（有评论了）；没填lift的也先纳入（靠RT的n<80再筛）
        if lift_dt and today < lift_dt:
            continue
        watching.append(k)
    return watching


def fill_yes(yes_asks, qty):
    """买YES qty张，从best(最低)ask逐档吃。
    自我防护：过滤非正size，并强制按价格升序（ask越低越好）。
    深度不足返回None。"""
    # 清洗：只保留 size>0 的档位
    levels = [[float(p), float(s)] for p, s in yes_asks if float(s) > 0]
    # 强制排序：ask 升序（最低价先吃）
    levels.sort(key=lambda x: x[0])
    need, cost = qty, 0.0
    for price, size in levels:
        take = min(need, size)
        cost += take * price
        need -= take
        if need <= 0:
            break
    return (cost / qty) if need <= 0 else None


def fill_no(yes_bids, qty):
    """买NO qty张=卖YES，从best(最高)bid逐档吃。
    自我防护：过滤非正size，并强制按价格降序（bid越高，卖YES越划算）。
    深度不足返回None。"""
    # 清洗：只保留 size>0 的档位
    levels = [[float(p), float(s)] for p, s in yes_bids if float(s) > 0]
    # 强制排序：bid 降序（最高价先吃，卖YES得最多）
    levels.sort(key=lambda x: -x[0])
    need, proceeds = qty, 0.0
    for price, size in levels:
        take = min(need, size)
        proceeds += take * price
        need -= take
        if need <= 0:
            break
    return (100 - proceeds / qty) if need <= 0 else None


# 模型缓存
_model_cache = {}


def model_result(score, n, base_rate):
    key = (score, n, base_rate)
    if key in _model_cache:
        return _model_cache[key]
    inp = ModelInputs(score_now=score, n_now=n, base_rate=base_rate,
                      prior_strength=PRIOR_STRENGTH,
                      n_final=max(FIXED_N_FINAL, n), drift=DRIFT)
    res = run_model(inp, n_sims=N_SIMS)
    _model_cache[key] = res
    return res


def check_movie(movie_key, notified):
    """检查一部片的所有门槛，打印符合条件的机会。notified: 已通知的(movie,floor)集合。"""
    m_cfg = config.WATCHLIST.get(movie_key, {})
    base_rate = m_cfg.get("base_rate")
    if base_rate is None:
        return
    base_rate = float(base_rate)

    # 1. RT 实时分数和评论数
    summary = fetch_summary_safe(movie_key)
    if summary is None:
        return
    score, n = summary["score"], summary["n"]
    name = summary.get("name", movie_key)

    if score is None or n is None:
        print(f"  {movie_key}: RT数据不全 (score={score}, n={n})")
        return
    print(f"  {name}: 分数={score} n={n}", end="")

    if n < N_MIN:
        print(f"  (n<{N_MIN}, 跳过)")
        return
    print()

    # 2. Kalshi 门槛列表（best价，初筛）
    event = m_cfg.get("kalshi_event")
    if not event:
        print(f"    ⚠ 无 kalshi_event，跳过")
        return
    try:
        rungs = kc.get_ladder_live(event)
    except Exception as e:
        print(f"    ⚠ 拿门槛失败: {e}")
        return

    res = model_result(score, n, base_rate)

    for r in rungs:
        floor = r.t
        if (movie_key, floor) in notified:
            continue

        yes_ask = r.yes_price
        no_ask = r.no_price
        yes_bid = 100 - no_ask   # no_ask = 100 - yes_bid
        spread = yes_ask - yes_bid

        prob_yes = res.prob_at_least(floor + 1)
        prob_no = 1 - prob_yes
        edge_yes = prob_yes * 100 - yes_ask
        edge_no = prob_no * 100 - no_ask

        # 初筛：方向 + 胜率 + edge + 买价
        candidate = None
        if DIRECTION in ("both", "yes_only") and \
           WIN_PROB_MIN <= prob_yes <= WIN_PROB_MAX and \
           EDGE_MIN <= edge_yes <= EDGE_MAX and yes_ask < PRICE_MAX:
            candidate = ("YES", edge_yes, prob_yes, yes_ask)
        elif DIRECTION in ("both", "no_only") and \
             WIN_PROB_MIN <= prob_no <= WIN_PROB_MAX and \
             EDGE_MIN <= edge_no <= EDGE_MAX and no_ask < PRICE_MAX:
            candidate = ("NO", edge_no, prob_no, no_ask)

        if candidate is None:
            continue
        if spread > SPREAD_MAX:
            continue

        direction, edge, win_prob, best_cost = candidate

        # 3. 拿逐档深度，算真实成本 + 深度检查
        ticker = r.ticker or f"{event}-{int(floor)}"   # 优先真实ticker，没有才拼接兜底
        depth_note = ""
        real_cost = best_cost
        try:
            ob = kc.fetch_market_orderbook(ticker)
            if direction == "YES":
                # 买YES吃yes_asks —— 但orderbook只有bids侧
                # yes的ask = no_bid价换算，用 no_bids 反推：yes_ask@X = no_bid@(100-X)
                # 简化：Kalshi只返回bids，买YES的深度要从no_bids换算
                asks = [[100 - p, s] for p, s in ob["no_bids"]]
                filled = fill_yes(asks, CONTRACTS)
            else:
                filled = fill_no(ob["yes_bids"], CONTRACTS)

            if filled is None:
                depth_note = f"⚠深度不足{CONTRACTS}张"
            else:
                real_cost = filled
                slip = real_cost - best_cost
                depth_note = f"真实成交{real_cost:.1f}¢(滑点{slip:+.1f}¢)"
        except Exception as e:
            depth_note = f"⚠深度查询失败: {e}"

        # 4. 打印机会
        print("    " + "★" * 20)
        print(f"    🎯 机会: {name}")
        print(f"       门槛 {direction} above {floor:.0f}")
        print(f"       模型胜率 {win_prob:.0%}  edge {edge:.0f}¢")
        print(f"       best买价 {best_cost:.0f}¢  {depth_note}")
        print(f"       当前分={score} n={n}  价差{spread:.0f}¢")
        print(f"       ticker: {ticker}")
        print("    " + "★" * 20)
        notified.add((movie_key, floor))


def main():
    print("=" * 60)
    print("盯盘启动")
    print(f"策略: n≥{N_MIN} 胜率{WIN_PROB_MIN:.0%}-{WIN_PROB_MAX:.0%} "
          f"edge{EDGE_MIN}-{EDGE_MAX} 买价<{PRICE_MAX}¢ 价差≤{SPREAD_MAX} "
          f"n_final={FIXED_N_FINAL} {DIRECTION}")
    print(f"间隔: {INTERVAL_MINUTES}分钟  |  Ctrl+C 停止")
    print("=" * 60)

    notified = set()
    cycle = 0
    try:
        while True:
            cycle += 1
            now = datetime.now(timezone.utc).astimezone()
            watching = get_watching_movies()
            print(f"\n[{now:%Y-%m-%d %H:%M:%S}] 第{cycle}轮  盯盘{len(watching)}部")
            for mk in watching:
                try:
                    check_movie(mk, notified)
                except Exception as e:
                    print(f"  ⚠ {mk} 检查出错: {e}")
            print(f"  本轮完成，已累计通知 {len(notified)} 个机会。等待{INTERVAL_MINUTES}分钟…")
            time.sleep(INTERVAL_MINUTES * 60)
    except KeyboardInterrupt:
        print("\n\n盯盘已停止。")
        sys.exit(0)


if __name__ == "__main__":
    main()