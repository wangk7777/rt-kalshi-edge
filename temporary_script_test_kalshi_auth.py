"""
验证"烂番茄晚期重力"假设：分数在评论积累后期是否系统性下跌。
对每部片，计算分数在 n=50/80/100 时 vs 最终分 的变化。
如果系统性为负（后期分数下跌），重力成立，解释了"买NO赚钱"。

用法：py test_gravity.py
"""
import glob, json, os
from datetime import datetime
from src import config

def parse_dt(s):
    try: return datetime.fromisoformat(str(s).replace("Z","+00:00"))
    except: return None

def is_fresh(r):
    s = str(r.get("sentiment",""))
    return "Fresh" in s or s.upper()=="POSITIVE"

def load(mk):
    p = os.path.join("data/historical", f"{mk}_fullpull.json")
    return json.load(open(p,encoding="utf-8")) if os.path.exists(p) else None

def score_at_n(reviews_sorted, n):
    """取前n条评论时的分数（fresh比例）。n超过总数返回None。"""
    if len(reviews_sorted) < n:
        return None
    subset = reviews_sorted[:n]
    fresh = sum(1 for r in subset if is_fresh(r))
    return fresh / n * 100

# 收集每部片在不同n的分数 + 最终分
checkpoints = [50, 80, 100, 150]
results = []  # (movie, n_check, score_at_check, final_score, delta)

for k, m in config.WATCHLIST.items():
    if m.get("exclude_from_backtest"): continue
    reviews = load(k)
    if not reviews: continue
    # 按时间排序
    rv = [(parse_dt(r.get("date")), r) for r in reviews if parse_dt(r.get("date"))]
    rv.sort(key=lambda x: x[0])
    reviews_sorted = [r for _, r in rv]
    total = len(reviews_sorted)
    if total < 50: continue

    final_fresh = sum(1 for r in reviews_sorted if is_fresh(r))
    final_score = final_fresh / total * 100

    for nc in checkpoints:
        s = score_at_n(reviews_sorted, nc)
        if s is not None:
            results.append({
                "movie": k, "n_check": nc, "score_at_check": s,
                "final_score": final_score, "final_n": total,
                "delta": final_score - s,   # 最终 - 当时；负=后期下跌
            })

# 分析：每个checkpoint的平均delta
print("="*60)
print("烂番茄晚期重力测试：分数从 n=X 到 最终分 的变化")
print("="*60)
print("delta = 最终分 - n=X时的分数。负值=后期下跌（重力存在）\n")

for nc in checkpoints:
    grp = [r for r in results if r["n_check"] == nc]
    if not grp:
        continue
    deltas = [r["delta"] for r in grp]
    avg_delta = sum(deltas) / len(deltas)
    down = sum(1 for d in deltas if d < -0.5)   # 下跌超过0.5分
    up = sum(1 for d in deltas if d > 0.5)
    flat = len(deltas) - down - up
    print(f"从 n={nc} 到最终（{len(grp)}部片）:")
    print(f"  平均变化: {avg_delta:+.2f}分  {'← 系统性下跌(重力!)' if avg_delta < -0.5 else '← 系统性上涨' if avg_delta > 0.5 else '← 基本不变'}")
    print(f"  下跌: {down}部 ({down*100//len(grp)}%) | 上涨: {up}部 ({up*100//len(grp)}%) | 持平: {flat}部")
    # 下跌幅度分布
    downs = sorted([d for d in deltas if d < -0.5])
    if downs:
        print(f"  下跌幅度: 中位{downs[len(downs)//2]:.1f}分, 最大跌{min(downs):.1f}分")
    print()

# 关键：高分片 vs 低分片，谁跌得多（重力对高分片更强？）
print("="*60)
print("按最终分高低看重力（用n=80的checkpoint）:")
print("="*60)
grp80 = [r for r in results if r["n_check"] == 80]
for lo, hi, name in [(0,60,"低分<60"),(60,80,"中分60-80"),(80,101,"高分80+")]:
    sub = [r for r in grp80 if lo <= r["final_score"] < hi]
    if sub:
        avg = sum(r["delta"] for r in sub)/len(sub)
        down = sum(1 for r in sub if r["delta"]<-0.5)
        print(f"  {name}: {len(sub)}部, 平均变化{avg:+.2f}分, 下跌{down}部({down*100//len(sub)}%)")