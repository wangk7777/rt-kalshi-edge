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
import re
import time
from datetime import datetime, date   # 直接导入类，代码里写 datetime.now() / date.today()

import requests

import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from src.strategy.decide import Rung

# 公开行情的基础 URL（这个子域虽然历史上叫 elections，但涵盖所有市场）
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

# events / candlesticks 等历史数据接口用的是另一个域名和路径
HIST_BASE_URL = "https://api.elections.kalshi.com/v1"

# 盘口快照目录
ORDERBOOKS_DIR = os.path.join("data", "orderbooks")

# ===== 签名认证（orderbook 等需认证的端点用）=====
# API key 和私钥是账户通用凭据，能给所有请求签名（不只 orderbook）。

def _load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()
_API_KEY_ID = os.environ.get("KALSHI_API_KEY")
_PRIVATE_KEY_PATH = "rt-kalshi-monitor-private-key.txt"
_private_key_cache = None


def _get_private_key():
    global _private_key_cache
    if _private_key_cache is None:
        if not os.path.exists(_PRIVATE_KEY_PATH):
            raise RuntimeError(f"私钥文件不存在: {_PRIVATE_KEY_PATH}")
        with open(_PRIVATE_KEY_PATH, "rb") as f:
            _private_key_cache = serialization.load_pem_private_key(f.read(), password=None)
    return _private_key_cache


def _sign(timestamp_ms: str, method: str, sign_path: str) -> str:
    """RSA-PSS 签名。message = timestamp + method + path"""
    message = f"{timestamp_ms}{method}{sign_path}".encode("utf-8")
    sig = _get_private_key().sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("utf-8")


def _get_signed(url: str, sign_path: str, params: dict | None = None,
                retries: int = 4) -> dict:
    """带签名的 GET（需认证的端点用，如 orderbook）。
    sign_path: 用于签名的路径，如 /trade-api/v2/markets/KXRT-SPI-90/orderbook
    """
    if not _API_KEY_ID:
        raise RuntimeError(".env 里没有 KALSHI_API_KEY")
    for attempt in range(retries):
        ts = str(int(time.time() * 1000))
        headers = {
            "KALSHI-ACCESS-KEY": _API_KEY_ID,
            "KALSHI-ACCESS-SIGNATURE": _sign(ts, "GET", sign_path),
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 429:
            wait = 2 ** attempt
            print(f"  [被限速，等 {wait} 秒重试…]")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("多次重试后仍被限速，放弃。")


def fetch_market_orderbook(ticker: str) -> dict:
    """
    拿单个门槛(market)的实时逐档 orderbook。返回解析后的档位。
    返回 {yes_bids: [[price_cent, size],...降序], no_bids: [[price_cent, size],...]}
    yes_bids 用于算买NO成本（NO成本 = 100 - yes_bid）。
    """
    path = f"/trade-api/v2/markets/{ticker}/orderbook"
    url = f"https://external-api.kalshi.com{path}"
    data = _get_signed(url, sign_path=path)
    ob = data.get("orderbook_fp", {}) or data.get("orderbook", {})

    def to_levels(arr):
        # [["0.0100","37286.43"],...] → [[1.0, 37286.43],...] 美元转美分
        return [[round(float(p) * 100, 2), float(s)] for p, s in (arr or [])]

    yes_bids = to_levels(ob.get("yes_dollars"))
    no_bids = to_levels(ob.get("no_dollars"))
    yes_bids.sort(key=lambda x: -x[0])   # 价格降序，best在前
    no_bids.sort(key=lambda x: -x[0])
    return {"yes_bids": yes_bids, "no_bids": no_bids, "ticker": ticker}


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
            ticker=m.get("ticker", ""),
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

# ===== 已结算历史片：从 events 接口拿所有门槛的元数据 =====
# 已结算市场 /markets 拉不到，但 /events/{event} 能返回（含已结算），
# 而且一次给全所有门槛的 market_id + 门槛值 + 结算结果 + 官方最终分数。

def fetch_event_markets(event_ticker: str) -> dict:
    """
    拿一个 event（一部电影）所有门槛的元数据。已结算的片也能拿。

    返回一个 dict：
      event_ticker   事件代码
      final_score    官方最终 RT 分数（从 expiration_value，所有门槛一致）
      settle_date    结算时刻（close_date，ISO 字符串）
      markets        门槛列表，每个含：
                       market_id  （拉 candlesticks 要用的 UUID）
                       floor      门槛数字（如 77）
                       result     结算结果 'yes'/'no'（None=还没结算）
                       status     市场状态（finalized/active 等）

    用法：fetch_event_markets("KXRTPRIMATE")
    """
    data = _get(f"{HIST_BASE_URL}/events/{event_ticker}")
    # 注意：events 接口在 /v1/ 下，不在 /trade-api/v2 下，所以单独拼 URL
    event = data.get("event", data)
    raw_markets = event.get("markets", [])
    if not raw_markets:
        raise RuntimeError(
            f"event '{event_ticker}' 没返回任何门槛。确认 event ticker 是否正确。"
        )

    markets = []
    for m in raw_markets:
        # 门槛值：优先用 floor_strike；有些片这个字段为空，
        # 门槛值藏在 ticker_name 末尾（如 KXRTDOGMAN-45 → 45），回退解析。
        floor = m.get("floor_strike")
        if floor is None:
            match = re.search(r'-(\d+)$', m.get("ticker_name", ""))
            floor = int(match.group(1)) if match else None
        if floor is None:
            continue   # 两种都拿不到才真的跳过
        markets.append({
            "market_id": m.get("id"),
            "ticker": m.get("ticker_name", ""),
            "floor": float(floor),
            "result": m.get("result"),
            "status": m.get("status"),
        })
    markets.sort(key=lambda x: x["floor"])
    if not markets:
        raise RuntimeError(f"'{event_ticker}' 有市场但没解析出门槛，字段可能变了。")

    # 官方最终分数和结算时刻：所有门槛一致，取第一个有值的
    final_score = None
    settle_date = None
    for m in raw_markets:
        if m.get("expiration_value") is not None and final_score is None:
            final_score = m.get("expiration_value")
        if m.get("close_date") is not None and settle_date is None:
            settle_date = m.get("close_date")

    # 开盘时刻：取所有门槛里【最早】的 open_date（防个别门槛晚开，最早的最保险）
    open_dates = [m.get("open_date") for m in raw_markets if m.get("open_date")]
    open_date = min(open_dates) if open_dates else None

    return {
        "event_ticker": event_ticker,
        "final_score": final_score,    # 官方最终 RT 分数（字符串，如 "77"）
        "settle_date": settle_date,    # 结算时刻 ISO（如 "2026-01-12T15:00:00Z"）
        "open_date": open_date,        # 开盘时刻 ISO（拉 candlesticks 的起点）
        "markets": markets,
    }

def fetch_candlesticks(series_ticker: str, market_id: str,
                       start_ts: int, end_ts: int,
                       period_interval: int = 60,
                       seg_days: int = 30) -> list[dict]:
    """
    拉某个门槛的历史盘口 K 线。已结算的也能拉（公开、免认证）。

    ⚠ candlesticks 接口对"单次时间跨度 × K线粒度"有上限，跨度太大会 400。
    所以这里【自动分段】：把 [start_ts, end_ts] 切成每段 seg_days 天，
    逐段拉再拼接。任何跨度都能完整拉到（如 deadpool 158 天分 6 段）。

    series_ticker: 系列代码 = config 里的 kalshi_event（如 "KXRTPRIMATE"）。
    market_id:     门槛的 UUID（从 fetch_event_markets 拿）。
    start_ts/end_ts: 时间范围，Unix 秒。
    period_interval: 每根 K 线分钟数，默认 60。
    seg_days:      每段多少天，默认 30（30天×24小时=720根，安全不超限）。

    返回 K 线列表（按时间顺序），每根含 ts/yes_ask/yes_bid/last_price/volume/open_interest。
    """
    SEG = seg_days * 24 * 3600
    all_candles: list[dict] = []

    # 关键修复：把时间戳向下取整到 period_interval 整数倍。
    # candlesticks 接口要求 start_ts/end_ts 对齐到K线边界，
    # 否则非整点的结算时间（如 14:26:53）会导致 400 Bad Request。
    step = period_interval * 60           # 60分钟 = 3600秒
    start_ts = (start_ts // step) * step  # 向下取整
    end_ts = (end_ts // step) * step + step   # 向上取整（多包一根，确保覆盖到结算）

    seg_start = start_ts
    while seg_start < end_ts:
        seg_end = min(seg_start + SEG, end_ts)
        url = (f"{HIST_BASE_URL}/series/{series_ticker}"
               f"/markets/{market_id}/candlesticks")
        data = _get(url, params={
            "start_ts": seg_start,
            "end_ts": seg_end,
            "period_interval": period_interval,
        })
        for c in data.get("candlesticks", []):
            all_candles.append({
                "ts": c["end_period_ts"],
                "yes_ask": c["yes_ask"]["close"],
                "yes_bid": c["yes_bid"]["close"],
                "last_price": c["price"]["close"],   # 可能 None
                "volume": c["volume"],
                "open_interest": c.get("open_interest"),
            })
        seg_start = seg_end

    return all_candles

def iso_to_ts(iso_str: str) -> int:
    """ISO 时间字符串（如 '2026-01-12T15:00:00Z'）→ Unix 秒。candlesticks 的 start_ts/end_ts 要用。"""
    s = str(iso_str).replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).timestamp())