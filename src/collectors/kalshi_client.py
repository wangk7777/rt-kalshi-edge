"""
Kalshi 价格采集器。

行情数据是公开的、不需要 API key（只有下单交易才要认证）。
我们用 /markets 端点，它直接返回每个 market 的 yes_ask / no_ask 等价格，
不用自己去解析 orderbook 反推。

电影门槛的层级：Series(KXRT) → Event(KXRT-TOY) → Market(KXRT-TOY-93)。
一部电影 = 一个 Event，它下面的各个门槛 = 各个 Market。所以我们按 event 过滤。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, date   # 直接导入类，代码里写 datetime.now() / date.today()

import requests

from src.strategy.decide import Rung

# 公开行情的基础 URL（这个子域虽然历史上叫 elections，但涵盖所有市场）
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

# 盘口快照目录
ORDERBOOKS_DIR = os.path.join("data", "orderbooks")


def get_ladder_manual(rows: list[tuple[float, float, float]]) -> list[Rung]:
    """从 (门槛, YES价, NO价) 元组列表构建 Rung 列表（手动价格，离线用）。"""
    return [Rung(t=t, yes_price=yp, no_price=np_) for (t, yp, np_) in rows]


def _get(url: str, params: dict | None = None, retries: int = 4) -> dict:
    """
    发一个 GET 请求并返回 JSON。带简单的指数退避：
    遇到 429(请求太频繁) 就等 1、2、4… 秒再重试。
    """
    for attempt in range(retries):
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 429:           # 被限速
            wait = 2 ** attempt               # 1, 2, 4, 8 秒
            print(f"  [被限速，等 {wait} 秒重试…]")
            time.sleep(wait)
            continue
        resp.raise_for_status()               # 其它错误（如 404）直接抛出
        return resp.json()
    raise RuntimeError("多次重试后仍被限速，放弃。")


def _cents(dollars):
    """美元字段 ×100 转美分；None 原样返回。"""
    return None if dollars is None else round(float(dollars) * 100, 1)


def find_movie_markets(keyword: str) -> None:
    """
    按关键词搜所有未平仓市场（自动翻页，搜全），打印匹配的 ticker、标题、价格。
    用法：find_movie_markets("toy story")
    """
    kw = keyword.lower()
    cursor = None          # 翻页书签，第一次为空
    found = False
    page = 0

    while True:
        params = {"limit": 1000, "status": "open"}
        if cursor:
            params["cursor"] = cursor      # 第二页开始带上书签
        data = _get(f"{BASE_URL}/markets", params=params)

        markets = data.get("markets", [])
        for m in markets:
            title = (m.get("title") or "") + " " + (m.get("subtitle") or "")
            if kw in title.lower() or kw in m.get("ticker", "").lower():
                found = True
                print(f"  {m['ticker']:<28} {m.get('title','')} "
                      f"[YES ask {m.get('yes_ask_dollars')}  "
                      f"event={m.get('event_ticker')}]")

        page += 1
        cursor = data.get("cursor")        # 拿下一页书签
        if not cursor or not markets:      # 没有下一页就停
            break
        if page > 30:                      # 保险：最多翻 30 页，防止万一翻不完
            print("  （翻了很多页，停在这里）")
            break

    if not found:
        print(f"  没找到含 '{keyword}' 的未平仓市场。"
              f"可能片名拼法不同，或市场还没开。")


def get_ladder_live(event_ticker: str) -> list[Rung]:
    """
    拉某部电影(event)所有门槛的实时价格，返回 Rung 列表。

    event_ticker: 这部片的事件代码，例如 'KXRT-TOY'。

    Kalshi 的字段说明：
      - 门槛数字在 floor_strike 字段（比从 ticker 解析更可靠）
      - 价格字段带 _dollars 后缀，单位是美元(0.12)，要 ×100 转成美分(12)
      - yes_ask_dollars = 做多要付的价；no_ask_dollars = 做空要付的价
    """
    data = _get(
        f"{BASE_URL}/markets",
        params={"event_ticker": event_ticker, "status": "open"},
    )
    markets = data.get("markets", [])
    if not markets:
        raise RuntimeError(
            f"event '{event_ticker}' 没返回任何未平仓市场。"
            f"先确认 event ticker 是否正确，或市场是否已开。"
        )

    rungs: list[Rung] = []
    for m in markets:
        # 门槛直接用 floor_strike 字段
        threshold = m.get("floor_strike")
        if threshold is None:
            continue

        # 价格带 _dollars 后缀、单位美元，×100 转成美分
        yes_ask = m.get("yes_ask_dollars")
        no_ask = m.get("no_ask_dollars")
        if yes_ask is None or no_ask is None:
            continue

        rungs.append(Rung(
            t=float(threshold),
            yes_price=float(yes_ask) * 100,   # 美元转美分
            no_price=float(no_ask) * 100,
        ))

    rungs.sort(key=lambda r: r.t)   # 按门槛从小到大排
    if not rungs:
        raise RuntimeError(
            f"找到了 '{event_ticker}' 的市场，但没解析出价格。字段名可能又变了。"
        )
    return rungs


# ===== 盘口快照（为 edge 回测攒数据）=====
# 比 get_ladder_live 多存 bid 和 volume：这些事后拿不到，现在不存以后就没了。

def fetch_orderbook(event_ticker: str) -> dict:
    """
    抓某部电影所有门槛的完整盘口（含 bid/ask/volume），返回一个 dict。

    和 get_ladder_live 的区别：那个只取 ask 给模型算 edge（轻量）；
    这个存全量（bid/ask/volume），是给【回测】留的历史证据，宁可多存。
    """
    data = _get(
        f"{BASE_URL}/markets",
        params={"event_ticker": event_ticker, "status": "open"},
    )
    markets = data.get("markets", [])
    if not markets:
        raise RuntimeError(
            f"event '{event_ticker}' 没返回未平仓市场（已结算的 API 可能不返回）。"
        )

    rungs = []
    for m in markets:
        threshold = m.get("floor_strike")
        if threshold is None:
            continue
        rungs.append({
            "threshold": float(threshold),
            # 价格都 ×100 存成美分；带 _dollars 的是美元
            "yes_ask": _cents(m.get("yes_ask_dollars")),
            "no_ask": _cents(m.get("no_ask_dollars")),
            "yes_bid": _cents(m.get("yes_bid_dollars")),
            "no_bid": _cents(m.get("no_bid_dollars")),
            "last_price": _cents(m.get("last_price_dollars")),
            "volume": m.get("volume_fp"),         # 累计成交量
            "open_interest": m.get("open_interest_fp"),
            "ticker": m.get("ticker", ""),
        })
    rungs.sort(key=lambda x: x["threshold"])

    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "event_ticker": event_ticker,
        "rungs": rungs,
    }


def save_orderbook(movie_key: str, snapshot: dict) -> str:
    """把盘口快照存成 data/orderbooks/{片}/{日期}.json，返回路径。"""
    folder = os.path.join(ORDERBOOKS_DIR, movie_key)
    os.makedirs(folder, exist_ok=True)
    today = date.today().isoformat()
    path = os.path.join(folder, f"{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=4)
    return path