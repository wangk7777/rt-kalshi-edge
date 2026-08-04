"""
盯盘脚本：实时监控当前上映电影，发现符合重力策略的交易机会，打印通知。

数据源：
- RT 实时分数/评论数：src.collectors.rt_summary
- Kalshi 门槛列表+best价：src.collectors.kalshi_client.get_ladder_live
- Kalshi 逐档深度：src.collectors.kalshi_client.fetch_market_orderbook
- 模型：src.model.bayesian

★ 策略参数从 config.STRATEGY_DEFAULTS 读取（集中管理）。
★ 支持单片覆盖：WATCHLIST 里某片若写了 n_final / win_prob_max 等小写字段，
  该片就用覆盖值，其余片用默认。见 config.get_strategy_params(movie_key)。

盯盘范围：watchlist 里 已解禁 <= 今天 < settle_date 的片（自动筛，零维护）。
新片加进 config 自动纳入，结算后自动退出。
同一(电影,门槛)通知一次后，只有 edge 显著变好才再次提醒。
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

# ============ 盯盘专属参数（不进 config，只影响盯盘行为）============
CONTRACTS = 100                # 检查深度是否够买这么多张
DIRECTION = "both"             # both / yes_only / no_only
EDGE_IMPROVE_THRESHOLD = 3.0   # edge 比上次提醒时高出这么多¢，才再次提醒（防小波动轰炸）
INTERVAL_MINUTES = 15          # 循环间隔（分钟）
DEBUG = True                  # True 打印每个门槛的 prob/edge（诊断为什么没机会）
# 策略参数（DRIFT/PRIOR/N_MIN/WIN_PROB/EDGE/SPREAD/N_FINAL/N_SIMS）
# 全部来自 config.STRATEGY_DEFAULTS，并支持单片覆盖，见 check_movie。
# ==================================================================


def parse_dt(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def should_watch(settle_date, embargo_date, today):
    """判断一部片当前是否该盯。纯函数，便于测试。
    embargo_date: 解禁日（config 的 embargo_date 或 lift_date，谁有用谁）。"""
    settle_dt = parse_dt(settle_date if "T" in str(settle_date)
                         else str(settle_date) + "T14:00:00Z")
    if settle_dt is None:
        return False
    if today >= settle_dt:
        return False
    embargo_dt = parse_dt(str(embargo_date) + "T00:00:00Z") if embargo_date else None
    if embargo_dt and today < embargo_dt:
        return False
    return True


def get_watching_movies():
    """从 watchlist 筛出当前该盯的片。"""
    today = datetime.now(timezone.utc)
    watching = []
    for k, m in config.WATCHLIST.items():
        settle = m.get("kalshi_settle_date", "")
        lift = m.get("lift_date") or m.get("embargo_date")
        if should_watch(settle, lift, today):
            watching.append(k)
    return watching


def evaluate_rung(prob_yes, yes_ask, no_ask, params):
    """判断单个门槛是不是交易机会。纯函数，便于测试。
    params: 该片的策略参数 dict（来自 config.get_strategy_params）。
    返回 (方向, edge, 胜率, 买价) 或 None。"""
    prob_no = 1 - prob_yes
    yes_bid = 100 - no_ask
    spread = yes_ask - yes_bid
    if spread > params["SPREAD_MAX"]:
        return None
    if DIRECTION in ("both", "yes_only") and \
       params["WIN_PROB_MIN"] <= prob_yes <= params["WIN_PROB_MAX"] and \
       params["EDGE_MIN"] <= (prob_yes * 100 - yes_ask) <= params["EDGE_MAX"] and \
       yes_ask < params["PRICE_MAX"]:
        return ("YES", prob_yes * 100 - yes_ask, prob_yes, yes_ask)
    if DIRECTION in ("both", "no_only") and \
       params["WIN_PROB_MIN"] <= prob_no <= params["WIN_PROB_MAX"] and \
       params["EDGE_MIN"] <= (prob_no * 100 - no_ask) <= params["EDGE_MAX"] and \
       no_ask < params["PRICE_MAX"]:
        return ("NO", prob_no * 100 - no_ask, prob_no, no_ask)
    return None


def fill_yes(yes_asks, qty):
    """买YES qty张，从best(最低)ask逐档吃。
    自我防护：过滤非正size，并强制按价格升序（ask越低越好）。深度不足返回None。"""
    levels = [[float(p), float(s)] for p, s in yes_asks if float(s) > 0]
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
    自我防护：过滤非正size，并强制按价格降序（bid越高，卖YES越划算）。深度不足返回None。"""
    levels = [[float(p), float(s)] for p, s in yes_bids if float(s) > 0]
    levels.sort(key=lambda x: -x[0])
    need, proceeds = qty, 0.0
    for price, size in levels:
        take = min(need, size)
        proceeds += take * price
        need -= take
        if need <= 0:
            break
    return (100 - proceeds / qty) if need <= 0 else None


def is_valid_rt_data(score, n) -> bool:
    """校验RT返回的score和n是否合理。没解禁/API抽风时返回False。"""
    if score is None or n is None:
        return False
    try:
        score = float(score)
        n = int(n)
    except (ValueError, TypeError):
        return False
    if not (0 <= score <= 100):
        return False
    if n < 0:
        return False
    return True


# 模型缓存：key 含参数，避免不同片用不同参数时缓存串味
_model_cache = {}


def model_result(score, n, base_rate, params):
    """按 (score, n, base_rate, drift, prior, n_final, n_sims) 缓存模型结果。"""
    key = (score, n, base_rate, params["DRIFT"], params["PRIOR_STRENGTH"],
           params["N_FINAL"], params["N_SIMS"])
    if key in _model_cache:
        return _model_cache[key]
    inp = ModelInputs(score_now=score, n_now=n, base_rate=base_rate,
                      prior_strength=params["PRIOR_STRENGTH"],
                      n_final=max(params["N_FINAL"], n),   # n_final 不小于当前 n
                      drift=params["DRIFT"])
    res = run_model(inp, n_sims=params["N_SIMS"])
    _model_cache[key] = res
    return res


def check_movie(movie_key, notified):
    """检查一部片的所有门槛，打印符合条件的机会。
    notified: dict {(movie,floor): 上次提醒时的edge}。"""
    m_cfg = config.WATCHLIST.get(movie_key, {})
    base_rate = m_cfg.get("base_rate")
    if base_rate is None:
        return
    base_rate = float(base_rate)

    # ★ 取该片的策略参数（支持单片覆盖）★
    params = config.get_strategy_params(movie_key)

    # 1. RT 实时分数和评论数
    summary = fetch_summary_safe(movie_key)
    if summary is None:
        return
    score, n = summary["score"], summary["n"]
    name = summary.get("name", movie_key)

    if not is_valid_rt_data(score, n):
        print(f"  {name or movie_key}: RT数据异常 (score={score}, n={n})，跳过")
        return
    score, n = float(score), int(n)
    print(f"  {name}: 分数={score:.0f} n={n}", end="")

    if n < params["N_MIN"]:
        print(f"  (n<{params['N_MIN']}, 跳过)")
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

    res = model_result(score, n, base_rate, params)

    for r in rungs:
        floor = r.t
        yes_ask = r.yes_price
        no_ask = r.no_price
        yes_bid = 100 - no_ask
        spread = yes_ask - yes_bid

        prob_yes = res.prob_at_least(floor + 1)
        prob_no = 1 - prob_yes

        candidate = evaluate_rung(prob_yes, yes_ask, no_ask, params)

        if candidate is None:
            if DEBUG:
                edge_yes = prob_yes * 100 - yes_ask
                edge_no = prob_no * 100 - no_ask
                # DEBUG时额外拿深度，看best ask挂了多少张
                ya_size, na_size = "?", "?"
                ticker = r.ticker or f"{event}-{int(floor)}"
                try:
                    ob = kc.fetch_market_orderbook(ticker)
                    # yes_ask@X 的挂单 = no_bid@(100-X) 的size
                    ya_size = sum(s for p, s in ob["no_bids"] if p == 100 - yes_ask)
                    # no_ask@Y 的挂单 = yes_bid@(100-Y) 的size
                    na_size = sum(s for p, s in ob["yes_bids"] if p == 100 - no_ask)
                except Exception:
                    pass   # 拿不到深度就显示?，不影响DEBUG
                print(f"    门槛{floor:.0f}: "
                      f"P_yes={prob_yes:.2f} yes_ask={yes_ask:.0f}(挂{ya_size}张) "
                      f"edge_yes={edge_yes:+.1f} | "
                      f"P_no={prob_no:.2f} no_ask={no_ask:.0f}(挂{na_size}张) "
                      f"edge_no={edge_no:+.1f} 价差{spread:.0f}")
            continue

        direction, edge, win_prob, best_cost = candidate

        # 去重：首次提醒，或 edge 比上次提醒时显著变好，才提醒
        key = (movie_key, floor)
        last_edge = notified.get(key)
        if last_edge is not None and edge < last_edge + EDGE_IMPROVE_THRESHOLD:
            continue

        # 3. 拿逐档深度，算真实成本 + 深度检查
        ticker = r.ticker or f"{event}-{int(floor)}"
        depth_note = ""
        real_cost = best_cost
        try:
            ob = kc.fetch_market_orderbook(ticker)
            if direction == "YES":
                # Kalshi 只返回 bids；买YES的深度从 no_bids 换算：yes_ask@X = no_bid@(100-X)
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
        print(f"       当前分={score:.0f} n={n}  价差{spread:.0f}¢")
        print(f"       ticker: {ticker}")
        print("    " + "★" * 20)
        notified[(movie_key, floor)] = edge   # 记录本次提醒的edge，供下次比较


def main():
    d = config.get_strategy_params()   # 打印默认参数概览
    print("=" * 60)
    print("盯盘启动")
    print(f"默认策略: n≥{d['N_MIN']} 胜率{d['WIN_PROB_MIN']:.0%}-{d['WIN_PROB_MAX']:.0%} "
          f"edge{d['EDGE_MIN']}-{d['EDGE_MAX']} 买价<{d['PRICE_MAX']}¢ "
          f"价差≤{d['SPREAD_MAX']} n_final={d['N_FINAL']} drift={d['DRIFT']} {DIRECTION}")
    print(f"（单片可在 WATCHLIST 覆盖 n_final 等参数）")
    print(f"间隔: {INTERVAL_MINUTES}分钟  |  DEBUG={DEBUG}  |  Ctrl+C 停止")
    print("=" * 60)

    notified = {}   # {(movie,floor): 上次提醒时的edge}
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