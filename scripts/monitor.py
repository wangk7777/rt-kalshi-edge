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

流程：
    1. 在kalshi/polymarket看到开了新盘-->在config的watchlist中填写对应信息
    2. 每日跑这个脚本，当有新电影解禁的时候就出现在
    3. 然后对于新解禁的电影，去rt官网跑rt_review_import_report.py里面写的java script脚本下载当前review raw数据
    4. 然后把下载的raw数据放到data/new_rt_review_data/raw/下面，运行rt_review_import_report.py脚本
    5. 阅读report并分析合理的n_final，修改config的watchlist里面的n_final字段
    6. 然后回来运行此脚本开始捕捉edge机会


用法：py -m scripts.monitor
"""

import time
import sys
from datetime import datetime, timezone

from src import config
from src.collectors.rt_summary import fetch_summary_safe
from src.model.bayesian import ModelInputs, run_model

# ============ 平台开关 ============
# "kalshi"     - 只盯 Kalshi（在美国时）
# "polymarket" - 只盯 Polymarket（回国后）
# "both"       - 两个都盯，分别打印
PLATFORM_MODE = "kalshi"
# ==================================

# ============ 盯盘专属参数（不进 config，只影响盯盘行为）============
CONTRACTS = 10                 # 检查深度是否够买这么多张
DIRECTION = "both"             # both / yes_only / no_only
EDGE_IMPROVE_THRESHOLD = 1.0   # edge 比上次提醒时高出这么多¢，才再次提醒（防小波动轰炸）
INTERVAL_MINUTES = 15          # 循环间隔（分钟）
COMPACT_MODE = False           # False=默认，打印每个门槛的细节；True=精简，只打印有机会的门槛
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


def get_settle_date_for_mode(m_cfg):
    """按当前 PLATFORM_MODE 取对应平台的结算日（都开盘取较晚的）。"""
    dates = []
    if PLATFORM_MODE in ("kalshi", "both") and m_cfg.get("kalshi_settle_date"):
        dates.append(str(m_cfg["kalshi_settle_date"]))
    if PLATFORM_MODE in ("polymarket", "both") and m_cfg.get("polymarket_settle_date"):
        dates.append(str(m_cfg["polymarket_settle_date"]))
    return max(dates) if dates else ""


def get_watching_movies():
    """从 watchlist 筛出当前该盯的片。
    只算：在当前 PLATFORM_MODE 平台上开盘 且 在盯盘时间窗内的片。"""
    today = datetime.now(timezone.utc)
    watching = []
    for k, m in config.WATCHLIST.items():
        # 先按平台过滤：这片在当前模式的平台上开盘吗（没开盘不算进盯盘数）
        if not get_active_platforms(m):
            continue
        settle = get_settle_date_for_mode(m)
        lift = m.get("lift_date") or m.get("embargo_date")
        if settle and should_watch(settle, lift, today):
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


def fill_asks(asks, qty):
    """从 asks（买入方向的卖单）逐档吃 qty 张，返回加权均价（美分）。
    自我防护：过滤非正size，强制按价格升序（越低越好）。深度不足返回None。
    买YES 传 yes_asks，买NO 传 no_asks——两个平台统一。"""
    levels = [[float(p), float(s)] for p, s in asks if float(s) > 0]
    levels.sort(key=lambda x: x[0])
    need, cost = qty, 0.0
    for price, size in levels:
        take = min(need, size)
        cost += take * price
        need -= take
        if need <= 0:
            break
    return (cost / qty) if need <= 0 else None


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


def get_active_platforms(m_cfg):
    """两层过滤：config填的字段（该片在哪些平台开盘）∩ PLATFORM_MODE 开关。"""
    available = config.get_platforms(m_cfg)   # 该片开盘的平台
    if PLATFORM_MODE == "both":
        return available
    return [p for p in available if p.name == PLATFORM_MODE]


def check_movie(movie_key, notified):
    """检查一部片：RT数据+模型算一次，遍历激活的平台分别检查打印。
    notified: dict {(platform, movie, floor): 上次提醒时的edge}。"""
    m_cfg = config.WATCHLIST.get(movie_key, {})
    base_rate = m_cfg.get("base_rate")
    if base_rate is None:
        return
    base_rate = float(base_rate)

    # 两层过滤：该片开盘的平台 ∩ 开关
    platforms = get_active_platforms(m_cfg)
    if not platforms:
        return   # 这片在想盯的平台上没开盘，跳过

    params = config.get_strategy_params(movie_key)

    # 1. RT 实时分数和评论数（平台无关，只拿一次）
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

    # 2. 模型算一次（平台无关）
    res = model_result(score, n, base_rate, params)

    # 3. 遍历激活的平台，分别检查
    for platform in platforms:
        _check_platform(platform, movie_key, m_cfg, name, res, score, n,
                        params, notified)


def _check_platform(platform, movie_key, m_cfg, name, res, score, n, params, notified):
    """检查单个平台的所有门槛。"""
    try:
        rungs = platform.get_rungs(m_cfg)
    except Exception as e:
        print(f"    ⚠ [{platform.name}] 拿门槛失败: {e}")
        return
    if not rungs:
        return

    for r in rungs:
        floor = r.t
        yes_ask = r.yes_price
        no_ask = r.no_price
        # 用平台规则算 YES 概率（Kalshi floor+1，Polymarket floor）
        prob_yes = platform.yes_prob(res, floor)
        prob_no = 1 - prob_yes
        yes_bid = 100 - no_ask
        spread = yes_ask - yes_bid
        edge_yes = prob_yes * 100 - yes_ask
        edge_no = prob_no * 100 - no_ask

        candidate = evaluate_rung(prob_yes, yes_ask, no_ask, params)

        # 细节行（默认打印每个门槛）
        detail = (f"    [{platform.name}] 门槛{floor:.0f}: "
                  f"P_yes={prob_yes:.2f} yes_ask={yes_ask:.0f} edge_yes={edge_yes:+.1f} | "
                  f"P_no={prob_no:.2f} no_ask={no_ask:.0f} edge_no={edge_no:+.1f} "
                  f"价差{spread:.0f}")

        if candidate is None:
            # 无机会：默认模式打印细节行；精简模式跳过
            if not COMPACT_MODE:
                print(detail)
            continue

        # 有机会：去重判断
        direction, edge, win_prob, best_cost = candidate
        key = (platform.name, movie_key, floor)
        last_edge = notified.get(key)
        is_new = last_edge is None or edge >= last_edge + EDGE_IMPROVE_THRESHOLD

        if not is_new:
            # 已提醒过且edge没显著变好：当普通门槛处理（默认打印细节行，不重复标★轰炸）
            if not COMPACT_MODE:
                print(detail)
            continue

        # 新机会：拿深度算真实成本
        depth_note = ""
        try:
            depth = platform.fetch_depth(r, m_cfg)
            asks = depth["yes_asks"] if direction == "YES" else depth["no_asks"]
            filled = fill_asks(asks, CONTRACTS)
            if filled is None:
                depth_note = f"深度不足{CONTRACTS}张"
            else:
                slip = filled - best_cost
                depth_note = f"买{CONTRACTS}张均价{filled:.1f}¢(滑点{slip:+.1f}¢)"
        except Exception as e:
            depth_note = f"深度查询失败: {e}"

        # 细节行 + 行尾★标记（精简模式也打印有机会的行）
        rule_hint = f"≥{int(floor)+1}" if platform.name == "kalshi" else f"≥{int(floor)}"
        print(f"{detail}  ★ 机会:{direction}({rule_hint})")
        notified[key] = edge


def main():
    d = config.get_strategy_params()   # 打印默认参数概览
    print("=" * 60)
    print("盯盘启动")
    print(f"默认策略: n≥{d['N_MIN']} 胜率{d['WIN_PROB_MIN']:.0%}-{d['WIN_PROB_MAX']:.0%} "
          f"edge{d['EDGE_MIN']}-{d['EDGE_MAX']} 买价<{d['PRICE_MAX']}¢ "
          f"价差≤{d['SPREAD_MAX']} n_final={d['N_FINAL']} drift={d['DRIFT']} {DIRECTION}")
    print(f"（单片可在 WATCHLIST 覆盖 n_final 等参数）")
    print(f"间隔: {INTERVAL_MINUTES}分钟  |  平台: {PLATFORM_MODE}  |  精简模式={COMPACT_MODE}  |  Ctrl+C 停止")
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