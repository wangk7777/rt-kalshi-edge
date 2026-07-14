"""
烂番茄评论采集器（能力模块）。

和 kalshi_client.py 并列：kalshi_client 抓价格，rt_reviews 抓评论，
两者都是"和外部世界打交道、获取数据"的采集层。

这个文件只提供【能力】（怎么抓、怎么存），不解析命令行、不打印报告，
也不做打分换算（换算属于分析层 analysis/reviews.py，保持采集层干净）。

数据来自 RT 的内部 API（F12 → 网络 → Fetch/XHR → 搜 reviews 找到的）。
每部电影有一个专属 UUID，存在 config.WATCHLIST 的 rt_movie_id 字段里。
"""

from __future__ import annotations

import datetime
import html   # 标准库：把 HTML 实体（&#44; &quot; 等）解码回正常标点
import json
import os
import time

import requests

# 伪装成正常浏览器，否则 RT 可能拒绝脚本请求
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# 评论快照目录（按片分子文件夹）
SNAPSHOTS_DIR = os.path.join("data", "snapshots")
# 历史片全量存档目录
HISTORICAL_DIR = os.path.join("data", "historical")


def fetch_reviews(rt_movie_id: str) -> list[dict]:
    """
    抓某部电影所有影评人评论，自动翻页，返回评论列表。

    rt_movie_id: 这部片的 RT 内部 UUID。
    返回：每条评论是个 dict，含以下字段：
      critic        影评人名
      is_top_critic 是否顶级影评人（顶级影评人意见权重高，可能领导风向）
      media         媒体名
      sentiment     Fresh/Rotten（RT 官方判定，结算口径就看这个）
      score         原始打分（如 "8/10" "B" "4/5"），换算交给分析层
      date          发布时间（ISO 字符串，如 "2026-06-21T18:41:17.000Z"）
      quote         评论原文（已 HTML 解码）
      url           评论原文链接（溯源用）
    """
    base_url = (
        f"https://www.rottentomatoes.com/napi/rtcf/v1/movies/"
        f"{rt_movie_id}/reviews"
    )

    all_reviews: list[dict] = []
    cursor = ""
    page_num = 0
    MAX_PAGE_RETRY = 4       # 单页最多重试次数
    RETRY_WAIT = 15          # 每次重试等待秒数

    while True:
        page_num += 1
        params = {
            "type": "critic",
            "topOnly": "false",
            "pageCount": 50,
        }
        if cursor:
            params["after"] = cursor

        # 单页带重试：限速导致的异常返回会重试，而不是静默停止
        data = None
        for attempt in range(1, MAX_PAGE_RETRY + 1):
            try:
                resp = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
                resp.raise_for_status()
                d = resp.json()
            except Exception as e:
                if attempt >= MAX_PAGE_RETRY:
                    raise RuntimeError(
                        f"第{page_num}页请求失败{MAX_PAGE_RETRY}次（疑似限速），"
                        f"抓取中断，已抓{len(all_reviews)}条: {e}"
                    )
                print(f"  ⚠ 第{page_num}页请求异常，{RETRY_WAIT}秒后重试({attempt}/{MAX_PAGE_RETRY})")
                time.sleep(RETRY_WAIT)
                continue

            # 关键：检查返回结构是否完整。
            # 限速时 RT 可能返回 200 + 残缺内容（没有 pageInfo），
            # 旧代码会误判 has_next=False 静默停止 —— 这正是 deadpool 漏抓的原因。
            reviews = d.get("reviews")
            page_info = d.get("pageInfo")
            if reviews is None or page_info is None:
                if attempt >= MAX_PAGE_RETRY:
                    raise RuntimeError(
                        f"第{page_num}页返回结构异常{MAX_PAGE_RETRY}次（疑似限速），"
                        f"抓取中断，已抓{len(all_reviews)}条"
                    )
                print(f"  ⚠ 第{page_num}页返回残缺，{RETRY_WAIT}秒后重试({attempt}/{MAX_PAGE_RETRY})")
                time.sleep(RETRY_WAIT)
                continue

            data = d
            break   # 这一页正常拿到

        # 解析这一页
        for r in data.get("reviews", []):
            sentiment = r.get("scoreSentiment")
            critic = r.get("critic", {}) or {}
            pub = r.get("publication", {}) or {}
            quote_raw = r.get("reviewQuote", "（无具体文字）")
            all_reviews.append({
                "critic": critic.get("displayName", "匿名"),
                "is_top_critic": critic.get("isTopCritic", False),
                "media": pub.get("name", "未知媒体"),
                "sentiment": "Fresh 🍅" if sentiment == "POSITIVE" else "Rotten 🤢",
                "score": r.get("originalScore", "无具体打分"),
                "date": r.get("createDate", ""),
                "quote": html.unescape(quote_raw),
                "url": r.get("publicationReviewUrl", ""),
            })

        page_info = data["pageInfo"]
        has_next = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor", "")

        print(f"  已抓取 {len(all_reviews)} 条...")
        time.sleep(0.5)

        if not has_next:
            break   # 只有明确 hasNextPage=False 才正常结束

    return all_reviews


def save_reviews(movie_key: str, reviews: list[dict]) -> str:
    """
    存【每日快照】（金标准）：正在进行的片，每天一份。
    路径 data/snapshots/{片}/{日期}.json
    """
    folder = os.path.join(SNAPSHOTS_DIR, movie_key)
    os.makedirs(folder, exist_ok=True)
    today = datetime.date.today().isoformat()  # 例如 2026-06-21
    path = os.path.join(folder, f"{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=4)
    return path


def save_reviews_historical(movie_key: str, reviews: list[dict]) -> str:
    """
    存【历史片全量】（切片重建用）：已结算的片，抓一次全量。
    路径 data/historical/{片}_fullpull.json（不带日期戳）。
    历史片是固定的历史事实，重抓直接覆盖，不保留多个时间版本。
    文件名带 fullpull 标记，和金标准快照区分开——回测时知道这是重建数据。
    """
    os.makedirs(HISTORICAL_DIR, exist_ok=True)
    path = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=4)
    return path