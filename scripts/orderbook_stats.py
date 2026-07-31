"""
统计：按「解禁日美西12点 → 结算」切片后，orderbook 数据量会变成多少。
只统计，不修改任何文件。帮你决定瘦身后的存储方案。

解禁起点：embargo_date 当天 美西(America/Los_Angeles) 12:00 → 转UTC
结算终点：settle_date 14:00 UTC
深度档位：完整保留（不砍，为将来多门槛/Kelly策略留）

用法：py -m scripts.orderbook_stats
"""

import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src import config

OB_DIR = os.path.join("data", "orderbooks")
PACIFIC = ZoneInfo("America/Los_Angeles")


def embargo_cutoff_utc(embargo_date_str):
    """解禁日美西12:00 → UTC 时间戳(秒)。"""
    try:
        y, m, d = map(int, str(embargo_date_str)[:10].split("-"))
        local_noon = datetime(y, m, d, 12, 0, 0, tzinfo=PACIFIC)
        return local_noon.astimezone(timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def settle_cutoff_utc(settle_date_str):
    """结算日 14:00 UTC → 时间戳(秒)。"""
    try:
        s = str(settle_date_str)
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s[:10] + "T14:00:00+00:00")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def main():
    files = [f for f in os.listdir(OB_DIR) if f.endswith(".json")]
    print(f"📁 data/orderbooks/ 共 {len(files)} 个文件\n")

    total_size_before = 0
    total_snaps_before = 0
    total_snaps_after = 0
    est_size_after = 0
    per_movie = []
    no_embargo = []

    for fname in sorted(files):
        movie_key = fname[:-5]
        path = os.path.join(OB_DIR, fname)
        size_bytes = os.path.getsize(path)
        total_size_before += size_bytes

        m = config.WATCHLIST.get(movie_key, {})
        embargo = m.get("embargo_date")
        settle = m.get("kalshi_settle_date")

        emb_ts = embargo_cutoff_utc(embargo) if embargo else None
        set_ts = settle_cutoff_utc(settle)

        # 若无embargo_date，用该片最早快照当起点（不砍前面），记录待手工确认
        if emb_ts is None:
            no_embargo.append(movie_key)

        data = json.load(open(path, encoding="utf-8"))
        markets = data.get("markets", {})

        snaps_before = 0
        snaps_after = 0
        for ticker, mk in markets.items():
            hourly = mk.get("hourly_snapshots", {})
            for hk, snap in hourly.items():
                snaps_before += 1
                ts = snap.get("ts")
                if ts is None:
                    continue
                ts_sec = ts / 1000  # 快照ts是毫秒
                # 判断是否落在 [解禁, 结算] 窗口
                after_embargo = (emb_ts is None) or (ts_sec >= emb_ts)
                before_settle = (set_ts is None) or (ts_sec <= set_ts)
                if after_embargo and before_settle:
                    snaps_after += 1

        total_snaps_before += snaps_before
        total_snaps_after += snaps_after
        # 估算瘦身后体积（按快照比例）
        ratio = snaps_after / snaps_before if snaps_before else 0
        est_after = size_bytes * ratio
        est_size_after += est_after

        per_movie.append((movie_key, size_bytes, snaps_before, snaps_after, ratio, embargo))

    # 输出
    def mb(b): return b / 1024 / 1024

    print(f"{'电影':32}{'原大小MB':>10}{'原快照':>9}{'留存快照':>9}{'保留%':>7}  解禁日")
    print("-" * 90)
    for mk, sz, sb, sa, r, emb in per_movie:
        emb_str = emb if emb else "⚠无"
        print(f"{mk[:30]:32}{mb(sz):>10.1f}{sb:>9}{sa:>9}{r*100:>6.0f}%  {emb_str}")

    print("-" * 90)
    print(f"\n{'='*60}")
    print(f"总文件数: {len(files)}")
    print(f"当前总大小: {mb(total_size_before):.1f} MB ({mb(total_size_before)/1024:.2f} GB)")
    print(f"当前总快照数: {total_snaps_before:,}")
    print(f"切片后留存快照: {total_snaps_after:,} ({total_snaps_after*100//max(total_snaps_before,1)}%)")
    print(f"预估切片后大小: {mb(est_size_after):.1f} MB ({mb(est_size_after)/1024:.2f} GB)")
    print(f"预估节省: {mb(total_size_before - est_size_after):.1f} MB "
          f"({(1-est_size_after/max(total_size_before,1))*100:.0f}%)")
    print("=" * 60)

    if no_embargo:
        print(f"\n⚠ {len(no_embargo)} 部无 embargo_date（未砍前段，需确认）:")
        for k in no_embargo:
            print(f"    {k}")


if __name__ == "__main__":
    main()