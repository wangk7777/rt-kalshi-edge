"""诊断 toy_story_5 的切片：打印每个决策天的 lift_date、cutoff、n。"""
import json
from datetime import datetime, timezone, timedelta

def parse_dt(s):
    try: return datetime.fromisoformat(str(s).replace("Z","+00:00"))
    except: return None

reviews = json.load(open("data/historical/toy_story_5_fullpull.json", encoding="utf-8"))
dates = sorted([parse_dt(r.get("date")) for r in reviews if parse_dt(r.get("date"))])
print(f"总评论 {len(reviews)}, 最早 {dates[0]}, 最晚 {dates[-1]}")

# 看最早几天的评论分布
from collections import Counter
day_counts = Counter(d.date() for d in dates)
print("前几天评论分布:")
for day in sorted(day_counts)[:8]:
    print(f"  {day}: {day_counts[day]}条")

# 模拟切片（首日1条→次日逻辑）
earliest = dates[0]
first_day = earliest.date()
n_first = sum(1 for d in dates if d.date()==first_day)
if n_first == 1:
    lift_date = parse_dt((first_day+timedelta(days=1)).isoformat()+"T00:00:00Z")
else:
    lift_date = earliest
lift_date = lift_date.replace(hour=0,minute=0,second=0,microsecond=0)
print(f"\n解禁基准 lift_date={lift_date.date()} (首日{n_first}条)")

print("各决策天累计n:")
for d in [0,1,2,3,4,5]:
    cutoff = lift_date + timedelta(days=d, hours=23, minutes=59, seconds=59)
    n = sum(1 for dt in dates if dt <= cutoff)
    print(f"  第{d}天: cutoff={cutoff.date()} 23:59, 累计n={n}")