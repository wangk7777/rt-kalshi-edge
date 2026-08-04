"""
把 data/orderbooks/ 下的 40 个 orderbook 文件，切出 [解禁日美西12点, 结算14:00 UTC]
窗口内的每小时快照，合并成一个大文件 data/backtest/orderbooks_merged.json。

- 深度档位完整保留（给将来多门槛/Kelly策略用）
- 跳过空文件（如 minions_and_monsters）
- 结构：{ movie_key: { settle_date, final_score, markets: { ticker: {floor,result,hourly_snapshots} } } }

用法：py -m scripts.backtest.merge_orderbooks
"""

import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src import config

OB_DIR = os.path.join("data", "orderbooks")
OUT_DIR = os.path.join("data", "backtest")
OUT_PATH = os.path.join(OUT_DIR, "orderbooks_merged.json")
PACIFIC = ZoneInfo("America/Los_Angeles")


def embargo_cutoff_ms(embargo_date_str):
    """解禁日美西12:00 → UTC 毫秒时间戳。"""
    try:
        y, m, d = map(int, str(embargo_date_str)[:10].split("-"))
        local_noon = datetime(y, m, d, 12, 0, 0, tzinfo=PACIFIC)
        return int(local_noon.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def settle_cutoff_ms(settle_str):
    """结算 14:00 UTC → 毫秒时间戳。"""
    try:
        s = str(settle_str)
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s[:10] + "T14:00:00+00:00")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def get_embargo(movie_key):
    """取解禁日：优先 embargo_date，其次 lift_date。"""
    m = config.WATCHLIST.get(movie_key, {})
    return m.get("embargo_date") or m.get("lift_date")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(OB_DIR) if f.endswith(".json"))
    print(f"📁 待合并 {len(files)} 个文件\n")

    merged = {}
    stats = {"movies": 0, "skipped_empty": 0, "skipped_no_embargo": 0,
             "snaps_before": 0, "snaps_after": 0}

    for fname in files:
        movie_key = fname[:-5]
        data = json.load(open(os.path.join(OB_DIR, fname), encoding="utf-8"))
        markets = data.get("markets", {})

        # 跳过空文件
        total_snaps = sum(len(mk.get("hourly_snapshots", {})) for mk in markets.values())
        if total_snaps == 0:
            print(f"  ⏭  {movie_key}: 空文件，跳过")
            stats["skipped_empty"] += 1
            continue

        embargo = get_embargo(movie_key)
        settle = data.get("settle_date") or config.WATCHLIST.get(movie_key, {}).get("kalshi_settle_date")
        emb_ms = embargo_cutoff_ms(embargo) if embargo else None
        set_ms = settle_cutoff_ms(settle)

        if emb_ms is None:
            print(f"  ⚠ {movie_key}: 无解禁日，不切前段（全留到结算）")
            stats["skipped_no_embargo"] += 1

        # 切片
        movie_entry = {
            "settle_date": settle,
            "final_score": data.get("final_score"),
            "event_ticker": data.get("event_ticker"),
            "markets": {},
        }
        m_before = 0
        m_after = 0
        for ticker, mk in markets.items():
            hourly = mk.get("hourly_snapshots", {})
            kept = {}
            for hk, snap in hourly.items():
                m_before += 1
                ts = snap.get("ts")
                if ts is None:
                    continue
                after_emb = (emb_ms is None) or (ts >= emb_ms)
                before_set = (set_ms is None) or (ts <= set_ms)
                if after_emb and before_set:
                    kept[hk] = snap
                    m_after += 1
            if kept:
                movie_entry["markets"][ticker] = {
                    "floor": mk.get("floor"),
                    "result": mk.get("result"),
                    "hourly_snapshots": kept,
                }

        merged[movie_key] = movie_entry
        stats["movies"] += 1
        stats["snaps_before"] += m_before
        stats["snaps_after"] += m_after
        print(f"  ✓ {movie_key}: {m_before} → {m_after} 快照 "
              f"({len(movie_entry['markets'])} 门槛)")

    # 存
    json.dump(merged, open(OUT_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    size_mb = os.path.getsize(OUT_PATH) / 1024 / 1024
    print(f"\n{'='*55}")
    print(f"✅ 合并完成: {stats['movies']} 部电影")
    print(f"   跳过空文件: {stats['skipped_empty']}")
    print(f"   总快照: {stats['snaps_before']:,} → {stats['snaps_after']:,} "
          f"({stats['snaps_after']*100//max(stats['snaps_before'],1)}%)")
    print(f"   输出: {OUT_PATH}")
    print(f"   文件大小: {size_mb:.1f} MB")
    print("=" * 55)


if __name__ == "__main__":
    main()