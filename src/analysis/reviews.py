"""
评论分析层：对抓回来的评论数据做"评论质量报告"。
Review analysis layer: produce a review-quality report from scraped reviews.

不联网、不算交易概率，只做一件事：输入评论列表，输出结构化质量指标字典。
Pure function: list of reviews in, dict of metrics out. No IO, no trading math.

核心思想：Tomatometer 是二值的（fresh/rotten），把"勉强及格"和"真心好评"
都算成同一个 fresh。所以光看新鲜度看不出 93% 是扎实还是虚高。用原始打分补盲区。

重要原则 / Key principle：
fresh/rotten 一律以 RT 官方 sentiment 为准（结算口径如此）。
换算分数【只】用于质量分析，绝不用来重判 fresh/rotten。

报告分四大板块 / Four sections：
  1. 总览 Overview        —— 静态快照（总数、好评/差评、当前新鲜度）
  2. 影评人级别 Critic tier —— 顶级 vs 普通 新鲜度对比
  3. 打分质量 Score quality —— 平均/中位/脆弱好评/严重差评/分布
  4. 时间趋势合辑 Trends   —— 新鲜度(累计) + 平均分(累计) + 差评(独立)，共用日期桶
"""

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime

# ===== 打分 → 10 分制官方换算标准 =====
LETTER_TO_TEN = {
    "A+": 10.0, "A": 9.3, "A-": 8.6,
    "B+": 7.9,  "B": 7.1, "B-": 6.4,
    "C+": 5.7,  "C": 5.0, "C-": 4.3,
    "D+": 3.6,  "D": 2.9, "D-": 2.1,
    "F": 0.4,
}
FIVE_TO_TEN = {
    5.0: 10.0, 4.5: 9.0, 4.0: 8.0, 3.5: 7.0,
    3.0: 6.0, 2.5: 5.0, 2.0: 4.0, 1.5: 3.0, 1.0: 2.0, 0.5: 1.0,
}
FOUR_TO_TEN = {
    4.0: 10.0, 3.5: 8.75, 3.0: 7.5, 2.5: 6.25,
    2.0: 5.0, 1.5: 3.75, 1.0: 2.5, 0.5: 1.25,
}

# ===== 质量区间标准（写进报告）=====
BORDERLINE_LOW = 0.60    # 脆弱好评下界 = 6.0/10（fresh 及格线）
BORDERLINE_HIGH = 0.70   # 脆弱好评上界 = 7.0/10
SEVERE_ROTTEN = 0.50     # 严重差评线 = 5.0/10 以下


def parse_score(score: str) -> tuple[float | None, str]:
    """解析原始打分 → (归一化 0~1 或 None, 类型标签)。支持 10/字母/5星/4星。"""
    s = str(score).strip()
    if s in ("无具体打分", "", "N/A", "n/a"):
        return None, "none"
    m = re.match(r'^([0-9.]+)\s*/\s*10$', s)
    if m:
        return min(max(float(m.group(1)) / 10, 0.0), 1.0), "ten"
    if s in LETTER_TO_TEN:
        return LETTER_TO_TEN[s] / 10, "letter"
    m = re.match(r'^([0-9.]+)\s*/\s*5$', s)
    if m:
        stars = float(m.group(1))
        return min(max(FIVE_TO_TEN.get(stars, stars / 5 * 10) / 10, 0.0), 1.0), "five"
    m = re.match(r'^([0-9.]+)\s*/\s*4$', s)
    if m:
        stars = float(m.group(1))
        return min(max(FOUR_TO_TEN.get(stars, stars / 4 * 10) / 10, 0.0), 1.0), "four"
    return None, "other"


def _quality_label(v: float) -> str:
    if v >= 0.93: return "优秀 Excellent"
    if v >= 0.86: return "良好 Good"
    if v >= 0.79: return "挺好 Solid"
    if v >= 0.71: return "尚可 Decent"
    if v >= 0.60: return "脆弱 Borderline"
    return "差 Poor"


def _is_fresh(r):
    s = str(r.get("sentiment", ""))
    return "Fresh" in s or s.upper() == "POSITIVE"


def _is_rotten(r):
    s = str(r.get("sentiment", ""))
    return "Rotten" in s or s.upper() == "NEGATIVE"


def _parse_date(s):
    """ISO 时间字符串 → date 对象；失败返回 None。"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _bucket_key_fn(span_days: int):
    """根据跨度返回 (粒度名, 分桶函数)。<=14天按天 / <=90天按周 / 否则按月。"""
    if span_days <= 14:
        return "按天 by day", lambda d: d.isoformat()
    if span_days <= 90:
        return "按周 by week", lambda d: f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
    return "按月 by month", lambda d: f"{d.year}-{d.month:02d}"


def _build_trends(reviews: list[dict]) -> dict:
    """
    三张趋势共用一套日期桶：
      新鲜度  —— 累计（截止当天所有评论的 fresh 占比）；n 显示累计总数
      平均分  —— 累计（截止当天所有可换算打分的均值）；n 显示累计有效打分数
      差评    —— 独立（当天新增评论的差评占比）；n 显示当天新增数
    """
    dated = []
    for r in reviews:
        d = _parse_date(r.get("date"))
        if d is not None:
            dated.append((d, r))
    if not dated:
        return {"buckets": [], "granularity": None, "span_days": None}

    dated.sort(key=lambda x: x[0])
    first, last = dated[0][0], dated[-1][0]
    span = (last - first).days
    gran, key = _bucket_key_fn(span)

    # 先按桶归集每条评论
    buckets = OrderedDict()
    for d, r in dated:
        k = key(d)
        buckets.setdefault(k, [])
        buckets[k].append(r)

    rows = []
    cum_fresh = cum_total = 0          # 累计：新鲜度用
    cum_score_sum = cum_score_n = 0    # 累计：平均分用
    for k, group in buckets.items():
        # --- 当天独立：差评 ---
        day_n = len(group)
        day_rotten = sum(1 for r in group if _is_rotten(r))
        day_rotten_ratio = day_rotten / day_n if day_n else 0

        # --- 累计：新鲜度 ---
        cum_total += day_n
        cum_fresh += sum(1 for r in group if _is_fresh(r))
        cum_fresh_pct = cum_fresh / cum_total * 100 if cum_total else 0

        # --- 累计：平均分（只算可换算的打分）---
        for r in group:
            v, _ = parse_score(r.get("score", ""))
            if v is not None:
                cum_score_sum += v
                cum_score_n += 1
        cum_avg = (cum_score_sum / cum_score_n) if cum_score_n else None

        rows.append({
            "label": k,
            "day_n": day_n,                    # 当天新增（差评图用）
            "day_rotten_ratio": day_rotten_ratio,
            "cum_n": cum_total,                # 累计总数（新鲜度图用）
            "cum_fresh_pct": cum_fresh_pct,
            "cum_score_n": cum_score_n,        # 累计有效打分数（平均分图用）
            "cum_avg": cum_avg,
        })

    return {"buckets": rows, "granularity": gran, "span_days": span,
            "first_date": first.isoformat(), "last_date": last.isoformat()}


def build_report(reviews: list[dict]) -> dict:
    """对评论列表做质量分析，返回指标字典。"""
    n_total = len(reviews)
    if n_total == 0:
        return {"n_total": 0}

    fresh = sum(1 for r in reviews if _is_fresh(r))
    rotten = sum(1 for r in reviews if _is_rotten(r))
    tomatometer = fresh / n_total * 100

    precise_vals = []
    fmt = {"ten": 0, "letter": 0, "five": 0, "four": 0, "none": 0, "other": 0}
    for r in reviews:
        v, tag = parse_score(r.get("score", ""))
        fmt[tag] += 1
        if v is not None:
            precise_vals.append(v)
    n_precise = len(precise_vals)
    avg_score = sum(precise_vals) / n_precise if n_precise else None

    median_score = None
    if n_precise:
        sv = sorted(precise_vals)
        mid = n_precise // 2
        median_score = sv[mid] if n_precise % 2 else (sv[mid-1] + sv[mid]) / 2

    dist = {"差(<0.60)": 0, "脆弱(0.60-0.70)": 0, "尚可(0.70-0.79)": 0,
            "好(0.79-0.86)": 0, "优(>=0.86)": 0}
    for v in precise_vals:
        if v < 0.60: dist["差(<0.60)"] += 1
        elif v < 0.70: dist["脆弱(0.60-0.70)"] += 1
        elif v < 0.79: dist["尚可(0.70-0.79)"] += 1
        elif v < 0.86: dist["好(0.79-0.86)"] += 1
        else: dist["优(>=0.86)"] += 1

    fresh_precise = [v for v in precise_vals if v >= BORDERLINE_LOW]
    borderline_n = sum(1 for v in fresh_precise if BORDERLINE_LOW <= v < BORDERLINE_HIGH)
    borderline_ratio = borderline_n / len(fresh_precise) if fresh_precise else None
    severe_n = sum(1 for v in precise_vals if v < SEVERE_ROTTEN)

    top = [r for r in reviews if r.get("is_top_critic")]
    other = [r for r in reviews if not r.get("is_top_critic")]
    def fresh_rate(g):
        return (sum(1 for r in g if _is_fresh(r)) / len(g)) if g else None

    trends = _build_trends(reviews)

    return {
        "n_total": n_total, "fresh": fresh, "rotten": rotten,
        "tomatometer": tomatometer,
        "n_precise": n_precise, "fmt": fmt,
        "avg_score": avg_score, "median_score": median_score,
        "quality_label": _quality_label(avg_score) if avg_score else None,
        "dist": dist,
        "borderline_n": borderline_n, "borderline_total": len(fresh_precise),
        "borderline_ratio": borderline_ratio, "severe_n": severe_n,
        "top_n": len(top), "top_fresh": fresh_rate(top),
        "other_n": len(other), "other_fresh": fresh_rate(other),
        "trends": trends,
    }


def _disp_width(s: str) -> int:
    """计算字符串的显示宽度：中文/全角字符算 2，其余算 1。"""
    import unicodedata
    w = 0
    for ch in s:
        # 'F'(Fullwidth) 和 'W'(Wide) 是占两格的东亚宽字符
        w += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return w


def _pad(s: str, width: int) -> str:
    """按显示宽度左对齐补空格（认全角中文，避免条形起点参差不齐）。"""
    pad = width - _disp_width(s)
    return s + " " * max(pad, 0)


def _bar(value: float, vmax: float, width: int = 50) -> str:
    """纯 ASCII 横向条（选项 A）：只用 '#'，宽度 50，靠长度提精度。"""
    if vmax <= 0:
        return ""
    return "#" * round(value / vmax * width)


# ============ 打印：四大板块 ============

def print_report(report: dict) -> None:
    if report.get("n_total", 0) == 0:
        print("  （没有评论数据 / no reviews）")
        return
    r = report

    # ---- 板块 1：总览 ----
    print("【1】总览 Overview")
    print(f"  总评论数 Total      : {r['n_total']}")
    print(f"  好评/差评 Fresh/Rot : {r['fresh']} / {r['rotten']}")
    print(f"  当前新鲜度 Score    : {r['tomatometer']:.1f}%  (官方 sentiment)")

    # ---- 板块 2：影评人级别 ----
    print("\n【2】影评人级别 Critic tier")
    tf = f"{r['top_fresh']*100:.0f}%" if r['top_fresh'] is not None else "—"
    of = f"{r['other_fresh']*100:.0f}%" if r['other_fresh'] is not None else "—"
    print(f"  顶级 Top   : fresh {tf}  (n={r['top_n']})")
    print(f"  普通 Other : fresh {of}  (n={r['other_n']})")
    if r['top_fresh'] is not None and r['other_fresh'] is not None:
        gap = (r['other_fresh'] - r['top_fresh']) * 100
        if gap > 8:
            print(f"  ⚠ 顶级影评人更挑剔（低 {gap:.0f} 点），脆弱信号 / top critics harsher")
        else:
            print(f"  ✓ 两档接近 / tiers agree")

    # ---- 板块 3：打分质量 ----
    print("\n【3】打分质量 Score quality（10/字母/5星/4星 官方换算）")
    fc = r["fmt"]
    print(f"  精确样本 Sample : {r['n_precise']}/{r['n_total']}  "
          f"(10分{fc['ten']} 字母{fc['letter']} 5星{fc['five']} 4星{fc['four']})")
    print(f"  未纳入 Excluded : 无打分{fc['none']} + 其它{fc['other']}")
    if r["avg_score"] is not None:
        print(f"  平均分 Mean   : {r['avg_score']:.3f}  → {r['quality_label']}")
        print(f"  中位数 Median : {r['median_score']:.3f}  (抗极端值)")
        if r['borderline_ratio'] is not None:
            print(f"  脆弱好评 Borderline-fresh : {r['borderline_n']} 条 / 共 "
                  f"{r['borderline_total']} 条好评 = {r['borderline_ratio']*100:.1f}%")
            print(f"      └ 标准: 换算分 6.0~7.0 的好评（刚过 fresh 线，最易翻盘）")
        print(f"  严重差评 Severe rotten : {r['severe_n']} 条  └ 标准: 换算分 < 5.0")
        print(f"  打分分布 Distribution:")
        mx = max(r["dist"].values()) or 1
        for k, c in r["dist"].items():
            print(f"    {_pad(k, 18)} {c:3}  {_bar(c, mx)}")

    # ---- 板块 4：时间趋势合辑 ----
    t = r["trends"]
    print("\n【4】时间趋势合辑 Time trends")
    if not t["buckets"]:
        print("  无日期数据（需重新抓取带 date 的版本）/ no dates — re-scrape needed")
        return
    print(f"  {t['granularity']}，解禁 {t['first_date']} 起，跨度 {t['span_days']} 天")
    b = t["buckets"]

    # 4a 新鲜度（累计）
    print("\n  ▸ 新鲜度趋势 Tomatometer（累计 cumulative，n=累计总数）")
    fmax = max(x["cum_fresh_pct"] for x in b) or 1
    for x in b:
        print(f"    {x['label']:12} n={x['cum_n']:<4} {x['cum_fresh_pct']:5.1f}%  "
              f"{_bar(x['cum_fresh_pct'], fmax)}")

    # 4b 平均分（累计）
    print("\n  ▸ 平均分趋势 Mean score（累计 cumulative，n=累计有效打分）")
    avals = [x["cum_avg"] for x in b if x["cum_avg"] is not None]
    amax = max(avals) if avals else 1
    for x in b:
        if x["cum_avg"] is None:
            print(f"    {x['label']:12} n=0    —")
        else:
            print(f"    {x['label']:12} n={x['cum_score_n']:<4} {x['cum_avg']:.3f}  "
                  f"{_bar(x['cum_avg'], amax)}")

    # 4c 差评（独立）
    print("\n  ▸ 差评趋势 Rotten%（当天独立 per-day，n=当天新增）")
    rmax = max(x["day_rotten_ratio"] for x in b) or 1
    for x in b:
        warn = "  ⚠样本少" if x["day_n"] < 5 else ""
        print(f"    {x['label']:12} n={x['day_n']:<4} {x['day_rotten_ratio']*100:5.1f}%  "
              f"{_bar(x['day_rotten_ratio'], rmax)}{warn}")
    print(f"  方向 Direction:", _trend_verdict(b))


def _trend_verdict(buckets: list[dict]) -> str:
    """看当天差评比例（只取样本 >=5 的桶），比较首尾给方向。"""
    valid = [x for x in buckets if x["day_n"] >= 5]
    if len(valid) < 2:
        return "数据点太少，趋势不可靠 / too few solid points"
    diff = (valid[-1]["day_rotten_ratio"] - valid[0]["day_rotten_ratio"]) * 100
    if diff > 8:
        return f"⚠ 差评走高（+{diff:.0f}点），警惕口碑转向 / worsening"
    if diff < -8:
        return f"✓ 差评走低（{diff:.0f}点），口碑改善 / improving"
    return "✓ 大体稳定 / stable"