"""
从 Predexon 拉取 Kalshi sub-cent orderbook 历史快照。
数据从 2026-01-08 开始，只拉 settle_date >= 2026-01-08 的片。
每个门槛每小时保留一个代表快照（该小时最后一个，最接近HH:59:59）。
存各档 price/size（算滑点用）+ best bid/ask + depth。

用法：
  py -m scripts.archive_fetch.fetch_orderbooks                          # 全量（断点续传，已存在的跳过）
  py -m scripts.archive_fetch.fetch_orderbooks --movie minions_and_monsters   # 只抓一部，强制重抓覆盖

API key 从项目根 .env 读取（PREDEXON_API_KEY=...）
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from collections import OrderedDict

import requests

from src import config

PREDEXON_URL = "https://api.predexon.com/v2/kalshi/orderbooks-subcent"
CANDLES_DIR = os.path.join("data", "historical_candlesticks")
OUT_DIR = os.path.join("data", "orderbooks")
DATA_START_MS = int(datetime(2026, 1, 8, tzinfo=timezone.utc).timestamp() * 1000)
LIMIT = 2000
REQUEST_PAUSE = 0.15            # 每次请求间隔，礼貌限流


def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()
API_KEY = os.environ.get("PREDEXON_API_KEY")
if not API_KEY:
    raise SystemExit("❌ 没找到 PREDEXON_API_KEY。请在项目根 .env 里写 PREDEXON_API_KEY=你的key")

HEADERS = {"x-api-key": API_KEY}


def parse_iso_ms(s):
    """ISO时间字符串 → 毫秒时间戳。"""
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def fetch_ticker_orderbooks(ticker, start_ms, end_ms):
    """拉一个门槛在[start,end]的所有快照，分页拉完。返回 [(ts_ms, snapshot), ...]。"""
    all_snaps = []
    pagination_key = None
    pages = 0
    while True:
        params = {
            "ticker": ticker,
            "start_time": start_ms,
            "end_time": end_ms,
            "limit": LIMIT,
        }
        if pagination_key:
            params["pagination_key"] = pagination_key
        try:
            resp = requests.get(PREDEXON_URL, params=params, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"      ⚠ 请求异常 {ticker}: {e}，等2秒重试")
            time.sleep(2)
            continue
        if resp.status_code == 429:   # 限流
            print(f"      ⏳ 限流，等5秒")
            time.sleep(5)
            continue
        if resp.status_code != 200:
            print(f"      ⚠ {ticker} HTTP {resp.status_code}: {resp.text[:120]}")
            break
        data = resp.json()
        snaps = data.get("snapshots", [])
        for s in snaps:
            all_snaps.append((s["timestamp"], s))
        pages += 1
        pag = data.get("pagination", {})
        if pag.get("has_more") and pag.get("pagination_key"):
            pagination_key = pag["pagination_key"]
            time.sleep(REQUEST_PAUSE)
        else:
            break
    return all_snaps


def hourly_representative(snapshots):
    """每个自然小时保留最后一个快照（最接近HH:59:59）。"""
    buckets = OrderedDict()
    for ts_ms, snap in sorted(snapshots, key=lambda x: x[0]):
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        hour_key = dt.strftime("%Y-%m-%d %H:00")
        buckets[hour_key] = snap   # 后覆盖前 = 保留该小时最后一个
    return buckets


def slim_snapshot(snap):
    """精简快照，只留交易需要的：best bid/ask、depth、各档price/size。"""
    def levels(arr):
        return [[lvl["price"], lvl["size"]] for lvl in arr]
    return {
        "ts": snap["timestamp"],
        "best_bid": snap.get("best_bid"),
        "best_ask": snap.get("best_ask"),
        "bid_depth": snap.get("bid_depth"),
        "ask_depth": snap.get("ask_depth"),
        "yes_bids": levels(snap.get("yes_bids", [])),   # [[price,size],...] 降序
        "yes_asks": levels(snap.get("yes_asks", [])),   # 升序
    }


def build_targets(single_movie=None):
    """构建要抓取的电影列表。single_movie 指定时只返回那一部。"""
    targets = []
    for k, m in config.WATCHLIST.items():
        if m.get("exclude_from_backtest"):
            continue
        sd = m.get("kalshi_settle_date", "")
        sd_ms = parse_iso_ms(sd if "T" in str(sd) else str(sd) + "T14:00:00Z")
        if sd_ms is None or sd_ms < DATA_START_MS:
            continue
        targets.append((k, m, sd_ms))

    if single_movie:
        # 单片模式：先从正常列表找
        filtered = [t for t in targets if t[0] == single_movie]
        if filtered:
            return filtered
        # 若被 settle_date 过滤掉了，直接从 WATCHLIST 构造（兜底）
        m = config.WATCHLIST.get(single_movie)
        if m is None:
            raise SystemExit(f"❌ config 里没有 movie_key: {single_movie}")
        sd = m.get("kalshi_settle_date", "")
        sd_ms = parse_iso_ms(sd if "T" in str(sd) else str(sd) + "T14:00:00Z")
        return [(single_movie, m, sd_ms)]

    return targets


def fetch_one_movie(movie_key, m, settle_ms, idx, total):
    """抓取一部电影的全部门槛，返回是否成功。"""
    # 读该片的 candlestick 拿 market tickers + 时间范围
    cpath = os.path.join(CANDLES_DIR, f"{movie_key}.json")
    if not os.path.exists(cpath):
        print(f"[{idx}/{total}] {movie_key} 无candlestick，跳过（无法拿到门槛ticker）")
        return False
    cdata = json.load(open(cpath, encoding="utf-8"))
    markets = cdata.get("markets", [])
    if not markets:
        print(f"[{idx}/{total}] {movie_key} 无markets，跳过")
        return False

    # 时间窗口：从数据起点(或该片最早candle) 到 结算
    earliest_candle_ts = None
    for mk in markets:
        for c in mk.get("candles", []):
            if c.get("ts"):
                t = c["ts"] * 1000
                if earliest_candle_ts is None or t < earliest_candle_ts:
                    earliest_candle_ts = t
    start_ms = max(DATA_START_MS, earliest_candle_ts or DATA_START_MS)
    end_ms = settle_ms if settle_ms else int(datetime.now(timezone.utc).timestamp() * 1000)

    print(f"[{idx}/{total}] {movie_key}: {len(markets)}个门槛, "
          f"{datetime.fromtimestamp(start_ms/1000,tz=timezone.utc).date()} → "
          f"{datetime.fromtimestamp(end_ms/1000,tz=timezone.utc).date()}")

    movie_ob = {
        "movie_key": movie_key,
        "event_ticker": cdata.get("event_ticker"),
        "settle_date": m.get("kalshi_settle_date"),
        "final_score": cdata.get("final_score"),
        "markets": {},
    }

    total_snaps = 0
    for mk in markets:
        ticker = mk.get("ticker")
        floor = mk.get("floor")
        if not ticker:
            continue
        snaps = fetch_ticker_orderbooks(ticker, start_ms, end_ms)
        hourly = hourly_representative(snaps)
        slimmed = {hk: slim_snapshot(s) for hk, s in hourly.items()}
        movie_ob["markets"][ticker] = {
            "floor": floor,
            "result": mk.get("result"),
            "hourly_snapshots": slimmed,
        }
        total_snaps += len(snaps)
        print(f"    {ticker} (floor={floor}): {len(snaps)}快照 → {len(slimmed)}小时")
        time.sleep(REQUEST_PAUSE)

    if total_snaps == 0:
        print(f"    ⚠ {movie_key} 所有门槛都是0快照 —— Predexon可能无此片数据，未写文件")
        return False

    out_path = os.path.join(OUT_DIR, f"{movie_key}.json")
    json.dump(movie_ob, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"    💾 存 {out_path}\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="拉取 Kalshi sub-cent orderbook")
    parser.add_argument("--movie", type=str, default=None,
                        help="只抓某一部电影的 movie_key（强制重抓，覆盖已有文件）")
    args = parser.parse_args()
    single_movie = args.movie

    os.makedirs(OUT_DIR, exist_ok=True)

    targets = build_targets(single_movie)

    if single_movie:
        print(f"🎯 单片模式：只抓 {single_movie}（强制重抓）\n")
    else:
        print(f"🎯 {len(targets)} 部片 settle_date >= 2026-01-08，可拉orderbook\n")

    ok = 0
    fail = 0
    for idx, (movie_key, m, settle_ms) in enumerate(targets, 1):
        out_path = os.path.join(OUT_DIR, f"{movie_key}.json")
        # 断点续传：非单片模式下，已存在则跳过；单片模式强制重抓
        if os.path.exists(out_path) and not single_movie:
            print(f"[{idx}/{len(targets)}] {movie_key} 已存在，跳过（断点续传）")
            continue
        try:
            if fetch_one_movie(movie_key, m, settle_ms, idx, len(targets)):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            print(f"    ❌ {movie_key} 抓取出错: {e}")
            fail += 1

    print(f"✅ 完成：成功 {ok} 部，失败/无数据 {fail} 部")


if __name__ == "__main__":
    main()