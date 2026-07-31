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
import html
import json
import os
import time

import requests

# RT 数据目录
SNAPSHOTS_DIR = os.path.join("data", "snapshots")
HISTORICAL_DIR = os.path.join("data", "historical")

MAX_PAGE_RETRY = 4
RETRY_WAIT = 15        # 限速类错误的重试等待（秒）

# 可选：防爬 cookie。若纯 Referer 不够（还 401），从浏览器复制那个防爬 cookie 填这里。
# 注意：这种 cookie 会过期，过期后需重新复制。留空则不带 cookie。
RT_COOKIE = "eXr91Jra=A13VfeeeAQAAVGSpo4fI8KIpyTQDso2r-4pVOn4XkbRy3ht219VrVxGekUX1AWu-_oSucsiSwH8AAEB3AAAAAA|1|1|37dd44b577a16c2a9df3cfe27c522cdbbb083ac9"


def _build_headers(movie_slug: str | None) -> dict:
    """构造请求头。关键是 Referer 指向该电影评论页。"""
    referer = "https://www.rottentomatoes.com/"
    if movie_slug:
        referer = f"https://www.rottentomatoes.com/m/{movie_slug}/reviews"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    if RT_COOKIE:
        headers["Cookie"] = RT_COOKIE
    return headers


def fetch_reviews(rt_movie_id: str, movie_slug: str | None = None) -> list[dict]:
    """
    抓某部电影所有影评人评论，自动翻页。
    rt_movie_id: RT 内部 UUID。
    movie_slug:  电影 URL slug（如 'toy_story_5'），用于构造 Referer。
                 强烈建议传入 movie_key，否则可能 401。
    """
    base_url = (
        f"https://www.rottentomatoes.com/napi/rtcf/v1/movies/"
        f"{rt_movie_id}/reviews"
    )
    headers = _build_headers(movie_slug)

    all_reviews: list[dict] = []
    has_next = True
    cursor = ""
    page_num = 0

    while has_next:
        page_num += 1
        params = {
            "type": "critic",
            "topOnly": "false",
            "pageCount": 50,
        }
        if cursor:
            params["after"] = cursor

        # 带重试的请求：401/403 认证问题不重试；限速/超时才重试
        attempt = 0
        data = None
        while True:
            attempt += 1
            try:
                resp = requests.get(base_url, headers=headers, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                if code in (401, 403):
                    # 认证被拒，重试无用，直接报错并给出诊断
                    raise RuntimeError(
                        f"第{page_num}页 {code} 认证被拒 —— RT 要求有效的 Referer/Cookie。\n"
                        f"  已带 Referer: {headers.get('Referer')}\n"
                        f"  是否带 Cookie: {'是' if 'Cookie' in headers else '否'}\n"
                        f"  若纯 Referer 不够，请设环境变量 RT_COOKIE=从浏览器复制的防爬cookie。\n"
                        f"  已抓 {len(all_reviews)} 条。原始错误: {e}"
                    )
                # 其它 HTTP 错误（如 429 限速）走重试
                if attempt >= MAX_PAGE_RETRY:
                    raise RuntimeError(
                        f"第{page_num}页请求失败{MAX_PAGE_RETRY}次（疑似限速），"
                        f"抓取中断，已抓{len(all_reviews)}条: {e}"
                    )
                print(f"  ⚠ 第{page_num}页 HTTP {code}，{RETRY_WAIT}秒后重试({attempt}/{MAX_PAGE_RETRY})")
                time.sleep(RETRY_WAIT)
            except (requests.RequestException, ValueError) as e:
                # 网络异常/JSON解析失败，也重试
                if attempt >= MAX_PAGE_RETRY:
                    raise RuntimeError(
                        f"第{page_num}页请求失败{MAX_PAGE_RETRY}次，"
                        f"抓取中断，已抓{len(all_reviews)}条: {e}"
                    )
                print(f"  ⚠ 第{page_num}页请求异常，{RETRY_WAIT}秒后重试({attempt}/{MAX_PAGE_RETRY})")
                time.sleep(RETRY_WAIT)

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

        page_info = data.get("pageInfo", {})
        has_next = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor", "")

        print(f"  已抓取 {len(all_reviews)} 条...")
        time.sleep(0.5)

    return all_reviews


def save_reviews(movie_key: str, reviews: list[dict]) -> str:
    folder = os.path.join(SNAPSHOTS_DIR, movie_key)
    os.makedirs(folder, exist_ok=True)
    today = datetime.date.today().isoformat()
    path = os.path.join(folder, f"{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=4)
    return path


def save_reviews_historical(movie_key: str, reviews: list[dict]) -> str:
    os.makedirs(HISTORICAL_DIR, exist_ok=True)
    path = os.path.join(HISTORICAL_DIR, f"{movie_key}_fullpull.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=4)
    return path