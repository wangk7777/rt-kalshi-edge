"""
实时抓取烂番茄电影的当前 Tomatometer 分数和影评人评论数。

用途：实盘盯盘 —— 只需要当前的 score 和 n 两个数字，用于实时跑模型判断。
区别于 rt_reviews.py（抓全部评论明细，用于回测历史数据集）。

抓取方式：请求 RT 主页面，解析其中的 JSON-LD 结构化数据。

★ 关键设计（避免抓错同名老片）：
  优先用 rt_movie_id(UUID) 构造 URL —— RT 会自动重定向到正确电影页。
  UUID 抓到正确页面后就用它的结果，**即使这部片还没影评（score/n 为 None）也不降级**。
  只有 UUID 请求本身失败（网络错误/404）时，才退到 slug。

  为什么这样：未上映的新片（如 digger_2026）用 UUID 能抓到正确页面，但没有
  aggregateRating（还没影评）。旧逻辑会因"没找到评分"降级到 slug，结果 slug
  (digger) 撞到同名老片、抓到老片的错误分数。新逻辑下，UUID 抓到正确片就认，
  没评分就返回 None，盯盘的 is_valid_rt_data 会正确跳过。

依赖：requests, beautifulsoup4
  pip install beautifulsoup4 --break-system-packages
"""

from __future__ import annotations

import json

import requests
from bs4 import BeautifulSoup

from src import config

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class RTSummaryError(Exception):
    """抓取失败（网络错误、页面无法访问、找不到Movie数据）。"""


def _parse_jsonld(html: str) -> dict:
    """
    从页面 HTML 的 JSON-LD 中提取电影信息。

    返回 {name, score, n}：
    - 找到 Movie 块且有评分 → score/n 有值
    - 找到 Movie 块但无评分（未上映/无影评）→ score=None, n=None，但 name 有值
    - 没找到 Movie 块 → 全 None

    注意：不抛异常。有没有评分都返回（让调用方决定怎么处理 None）。
    """
    result = {"name": None, "score": None, "n": None}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        movie = data if data.get("@type") == "Movie" else data.get("mainEntity", {})
        if not isinstance(movie, dict):
            continue
        # 找到 Movie 块
        result["name"] = movie.get("name")
        agg = movie.get("aggregateRating", {})
        if agg and agg.get("ratingValue") is not None:
            try:
                result["score"] = int(str(agg["ratingValue"]).replace("%", "").strip())
            except (ValueError, TypeError):
                result["score"] = None
            try:
                result["n"] = int(agg.get("reviewCount"))
            except (ValueError, TypeError):
                result["n"] = None
        return result   # 找到 Movie 块就返回（不管有没有评分）
    return result       # 没找到 Movie 块，全 None


def _fetch_url(url: str, timeout: int = 15) -> dict:
    """
    抓一个 RT 电影 URL。返回 {name, score, n, final_url}。
    请求失败（网络/HTTP错误）抛 RTSummaryError。
    页面能访问但没评分不算失败（score/n 为 None）。
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        raise RTSummaryError(f"HTTP {code}: {url}") from e
    except requests.RequestException as e:
        raise RTSummaryError(f"请求异常: {e}") from e

    parsed = _parse_jsonld(resp.text)
    parsed["final_url"] = resp.url
    return parsed


def fetch_summary(movie_key: str, timeout: int = 15) -> dict:
    """
    抓某部片的当前 score 和 n。给盯盘脚本调用。

    URL 优先级：
      1. rt_movie_id(UUID) —— 最可靠，RT 自动重定向到正确片。
         UUID 抓到正确页面就用，即使没评分（返回 None）也不降级。
      2. 只有 UUID 请求本身失败（网络/404）时，才退到 rt_slug 或 movie_key。

    返回 {movie_key, score, n, name, url_used, final_url}。
    score/n 可能为 None（未上映/无影评）—— 这是正常的，盯盘会跳过。
    完全无法抓取（所有 URL 都请求失败）时抛 RTSummaryError。
    """
    m = config.WATCHLIST.get(movie_key)
    if m is None:
        raise RTSummaryError(f"config 中无此电影: {movie_key}")

    uuid = m.get("rt_movie_id")
    slug = m.get("rt_slug") or movie_key

    # 1. 优先 UUID：抓到正确页面就用（即使没评分也不降级）
    if uuid:
        url = f"https://www.rottentomatoes.com/m/{uuid}"
        try:
            parsed = _fetch_url(url, timeout=timeout)
            parsed["movie_key"] = movie_key
            parsed["url_used"] = "uuid"
            return parsed
        except RTSummaryError:
            # UUID 请求本身失败（网络/404），才降级到 slug
            pass

    # 2. 退到 slug（仅当 UUID 不可用或请求失败）
    url = f"https://www.rottentomatoes.com/m/{slug}"
    parsed = _fetch_url(url, timeout=timeout)
    parsed["movie_key"] = movie_key
    parsed["url_used"] = "slug"
    return parsed


def fetch_summary_safe(movie_key: str) -> dict | None:
    """
    fetch_summary 的不抛异常版：请求失败返回 None（盯盘循环里用，一部失败不中断）。
    注意：抓到页面但没评分不算失败，会返回 {score:None, n:None,...}，由盯盘判断。
    """
    try:
        return fetch_summary(movie_key)
    except RTSummaryError as e:
        print(f"  ⚠ {movie_key}: {e}")
        return None


if __name__ == "__main__":
    import sys
    mk = sys.argv[1] if len(sys.argv) > 1 else "toy_story_5"
    try:
        r = fetch_summary(mk)
        print(f"电影: {r['name']}")
        print(f"分数(Tomatometer): {r['score']}")
        print(f"影评数(n): {r['n']}")
        print(f"用了: {r['url_used']}  最终URL: {r['final_url']}")
        if r["score"] is None:
            print("（无影评分数——可能未上映/还没影评，盯盘会跳过）")
    except RTSummaryError as e:
        print(f"失败: {e}")