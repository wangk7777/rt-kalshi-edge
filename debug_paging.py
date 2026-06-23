"""调试翻页：打印每页的 pageInfo，看翻页在哪停、为什么停。"""
import requests

RT_ID = "47d189ea-dcbd-3992-8cd0-86ff439aa52e"   # 从 config 复制过来

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
base = f"https://www.rottentomatoes.com/napi/rtcf/v1/movies/{RT_ID}/reviews"

cursor = ""
total = 0
page = 0
while True:
    params = {"type": "critic", "topOnly": "false", "pageCount": 50}
    if cursor:
        params["after"] = cursor
    data = requests.get(base, headers=HEADERS, params=params).json()

    reviews = data.get("reviews", [])
    total += len(reviews)
    page += 1
    page_info = data.get("pageInfo", {})

    print(f"第 {page} 页: 本页 {len(reviews)} 条, 累计 {total}")
    print(f"  pageInfo 完整内容: {page_info}")
    # 也把顶层所有 key 打出来，看 cursor/hasNextPage 到底叫什么
    print(f"  返回的顶层字段: {list(data.keys())}")

    has_next = page_info.get("hasNextPage", False)
    cursor = page_info.get("endCursor", "")
    print(f"  has_next={has_next}, endCursor={cursor!r}")
    print("-" * 50)

    if not has_next:
        print("→ 因为 hasNextPage=False 停止")
        break
    if not cursor:
        print("→ 因为 endCursor 为空停止")
        break
    if page > 10:
        print("→ 翻了10页强制停（防死循环）")
        break

print(f"\n总共抓到 {total} 条")