import json
import requests
from bs4 import BeautifulSoup


def fetch_movie_summary(movie_slug: str) -> dict | None:
    """
    抓烂番茄主页面的 JSON-LD，返回 {score, n} 或 None。
    score: Tomatometer新鲜度%（模型的score）
    n: 影评人评论数（模型的n）
    """
    url = f"https://www.rottentomatoes.com/m/{movie_slug}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        code = getattr(e.response, "status_code", None)
        print(f"  ⚠ {movie_slug} 抓取失败 HTTP {code}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
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
                score = int(str(agg["ratingValue"]).replace("%", ""))
            except (ValueError, TypeError):
                score = None
            n = agg.get("reviewCount")
            try:
                n = int(n)
            except (ValueError, TypeError):
                n = None
            return {"score": score, "n": n, "slug": movie_slug}

    print(f"  ⚠ {movie_slug} 未找到 JSON-LD 评分数据")
    return None


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "toy_story_5"
    r = fetch_movie_summary(slug)
    print(r)