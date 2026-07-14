"""诊断哪些片可能被限速抓漏：列出评论数 + 最早评论日期 vs 结算日。"""
import glob, json, os
from datetime import datetime, date
from src import config

HIST = "data/historical"

def pd(s):
    try: return datetime.fromisoformat(str(s).replace("Z","+00:00"))
    except: return None

def load(mk):
    # 兼容新旧文件名
    for pat in [f"{mk}_fullpull.json", f"{mk}_fullpull_*.json"]:
        files = glob.glob(os.path.join(HIST, pat))
        if files:
            with open(max(files), encoding="utf-8") as f:
                return json.load(f)
    return None

suspicious = []
for k, m in config.WATCHLIST.items():
    sd = m.get("kalshi_settle_date","")
    if not sd: continue
    try:
        if date.fromisoformat(sd[:10]) >= date.today(): continue
    except: continue
    reviews = load(k)
    if not reviews:
        continue
    dates = sorted([pd(r.get("date")) for r in reviews if pd(r.get("date"))])
    if not dates: continue
    earliest = dates[0].date()
    settle = date.fromisoformat(sd[:10])
    days_before = (settle - earliest).days
    n = len(reviews)
    # 可疑信号：最早评论距结算日太近（正常应该解禁在结算前1-3周）
    flag = ""
    if days_before < 5:
        flag = "⚠ 最早评论距结算<5天，疑似抓漏开头"
    print(f"{k:40} n={n:4}  最早={earliest}  结算前{days_before:3}天  {flag}")
    if flag:
        suspicious.append(k)

print(f"\n可疑（疑似抓漏）: {len(suspicious)} 部")
for s in suspicious:
    print(f"  {s}")