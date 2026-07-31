"""
实时抓取烂番茄电影的当前 Tomatometer 分数和影评人评论数。

用途：实盘盯盘 —— 只需要当前的 score 和 n 两个数字，用于实时跑模型判断。
区别于 rt_reviews.py（抓全部评论明细，用于回测历史数据集）。

抓取方式：请求 RT 主页面，解析其中的 JSON-LD 结构化数据。
优先用 rt_movie_id(UUID) 构造 URL —— RT 会自动重定向到正确电影页，
避免同名电影的 slug 歧义（如 wuthering_heights 会撞到老版本）。

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
    """抓取或解析失败。"""


def _parse_jsonld(html: str) -> dict | None:
    """从页面 HTML 的 JSON-LD 中提取 {name, score, n}。找不到返回 None。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        movie = data if data.get("@type") == "Movie" else data.get("mainEntity", {})
        if not isinstance(movie, dict):
            continue
        agg = movie.get("aggregateRating", {})
        if agg and agg.get("ratingValue") is not None:
            try:
                score = int(str(agg["ratingValue"]).replace("%", "").strip())
            except (ValueError, TypeError):
                score = None
            try:
                n = int(agg.get("reviewCount"))
            except (ValueError, TypeError):
                n = None
            return {"name": movie.get("name"), "score": score, "n": n}
    return None


def fetch_summary_by_url(url: str, timeout: int = 15) -> dict:
    """
    抓一个 RT 电影 URL，返回 {name, score, n, final_url}。
    失败抛 RTSummaryError。
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        raise RTSummaryError(f"HTTP {code} 抓取失败: {url}") from e
    except requests.RequestException as e:
        raise RTSummaryError(f"请求异常: {e}") from e

    parsed = _parse_jsonld(resp.text)
    if parsed is None:
        raise RTSummaryError(f"未找到 JSON-LD 评分数据: {resp.url}")
    parsed["final_url"] = resp.url
    return parsed


def fetch_summary(movie_key: str, timeout: int = 15) -> dict:
    """
    抓某部片的当前 score 和 n。给盯盘脚本调用。

    URL 选择：优先 rt_movie_id(UUID)（最可靠，RT 自动重定向到正确页），
    其次 rt_slug 字段，最后 movie_key。

    返回 {movie_key, score, n, name, url_used, final_url}。
    失败抛 RTSummaryError。
    """
    m = config.WATCHLIST.get(movie_key)
    if m is None:
        raise RTSummaryError(f"config 中无此电影: {movie_key}")

    uuid = m.get("rt_movie_id")
    slug = m.get("rt_slug") or movie_key

    # 优先 UUID（最可靠），失败再退到 slug
    attempts = []
    if uuid:
        attempts.append(("uuid", f"https://www.rottentomatoes.com/m/{uuid}"))
    attempts.append(("slug", f"https://www.rottentomatoes.com/m/{slug}"))

    last_err = None
    for kind, url in attempts:
        try:
            result = fetch_summary_by_url(url, timeout=timeout)
            result["movie_key"] = movie_key
            result["url_used"] = kind
            return result
        except RTSummaryError as e:
            last_err = e
            continue
    raise RTSummaryError(f"{movie_key} 所有方式都失败: {last_err}")


def fetch_summary_safe(movie_key: str) -> dict | None:
    """fetch_summary 的不抛异常版：失败返回 None（盯盘循环里用，一部失败不中断）。"""
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
    except RTSummaryError as e:
        print(f"失败: {e}")