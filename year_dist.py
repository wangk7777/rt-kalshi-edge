"""统计校准/验证切分用的年份分布。"""
import csv
from collections import defaultdict, Counter

with open("data/backtest/samples.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# 每部片一个结算日
movie_settle = {}
for r in rows:
    movie_settle[r["movie_key"]] = r["settle_date"]

by_month = defaultdict(list)
for mk, sd in movie_settle.items():
    by_month[sd[:7]].append(mk)

print(f"总电影数: {len(movie_settle)}")
print(f"总样本行: {len(rows)}\n")

by_year = Counter(sd[:4] for sd in movie_settle.values())
print("=== 按年（电影数）===")
for y in sorted(by_year):
    print(f"  {y}: {by_year[y]} 部")

row_by_year = Counter(r["settle_date"][:4] for r in rows)
print("\n=== 按年（样本行数）===")
for y in sorted(row_by_year):
    print(f"  {y}: {row_by_year[y]} 行")

print("\n=== 按月（电影数，累计）===")
cum = 0
for ym in sorted(by_month):
    cum += len(by_month[ym])
    print(f"  {ym}: {len(by_month[ym]):2}部  (累计{cum})")