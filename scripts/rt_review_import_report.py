"""
从 F12 手动复制的 RT 原始评论 JSON，转换成项目标准格式并出报告。
（绕过 Akamai 封锁的手动抓取方案）

流程：1. 去烂番茄网站上点击想要下载review的电影的review页面
      2. F12 → 网络 → 找到 reviews?after=XXXX 响应
      3. 进入控制台，复制以下代码，把最后一行的 uuid 和 movieKey 改成你要的电影的值，回车执行
      4. 会下载一个 <movieKey>_raw.json 文件，放到 data/new_rt_review_data/raw/ 下
      5. py -m scripts.rt_review_import_report <raw文件名> <movie_key> 
      6. 输出报告到 data/new_rt_review_data/report/<movie_key>_<日期>.txt，输出标准格式 JSON 到 data/new_rt_review_data/format/<movie_key>.json

在F12 console里执行以下代码（把最后一行的 uuid 和 movieKey 改成你要的电影的值）：

async function getAllReviews(uuid, movieKey) {
  const base = `https://www.rottentomatoes.com/napi/rtcf/v1/movies/${uuid}/reviews`;
  let all = [], page = 0;
  while (true) {
    const after = page === 0 ? "" : encodeURIComponent(btoa(String(page)));
    const url = `${base}?after=${after}&before=&pageCount=20&topOnly=false&type=critic&verified=false`;
    const data = await (await fetch(url)).json();
    const batch = data.reviews || data.results || [];
    all = all.concat(batch);
    console.log(`第${page+1}页: ${batch.length}条`);
    if (batch.length < 20) break;
    page++;
  }
  console.log(`总共 ${all.length} 条，正在下载文件...`);
  // 直接下载成 json 文件
  const blob = new Blob([JSON.stringify(all, null, 2)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${movieKey}_raw.json`;
  a.click();
}
//只需在这里输入电影的 uuid 和 movieKey（movieKey 见 config.WATCHLIST的id）
getAllReviews("65e185e4-e760-39d5-a518-19df8cc56275", "ice_cream_man");


目录结构（都在 data/new_rt_review_data/ 下）：
  raw/     ← 你把 F12 复制的原始评论 JSON 放这里
  format/  ← 脚本输出转换后的项目标准格式 JSON
  report/  ← 脚本输出报告 txt（文件名 = 电影名+日期）


输出：
  data/new_rt_review_data/format/<movie_key>.json
  data/new_rt_review_data/report/<movie_key>_<日期>.txt
  + 终端打印同样的报告
"""
import json
import os
import sys
import html
from datetime import datetime, timezone
 
from src import config
from src.analysis.reviews import build_report, print_report
from src.model.bayesian import ModelInputs, run_model
 
BASE_DIR = os.path.join("data", "new_rt_review_data")
RAW_DIR = os.path.join(BASE_DIR, "raw")
FORMAT_DIR = os.path.join(BASE_DIR, "format")
REPORT_DIR = os.path.join(BASE_DIR, "report")
 
 
class Tee:
    """把写入同时分发到多个流（终端 + 文件），实现边打印边存。"""
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
    def flush(self):
        for s in self.streams:
            s.flush()
 
 
def extract_reviews(raw):
    """从各种可能的外层结构里提取评论数组。"""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("reviews", "reviewList", "data", "results"):
            if key in raw:
                inner = raw[key]
                if isinstance(inner, list):
                    return inner
                if isinstance(inner, dict):
                    return extract_reviews(inner)
    raise SystemExit("无法从输入里找到评论数组。请确认复制的是 reviews 响应。")
 
 
def convert_one(r):
    """RT 原始格式 → 项目标准格式。"""
    critic = r.get("critic") or {}
    pub = r.get("publication") or {}
    quote = r.get("reviewQuote", "")
    if quote:
        quote = html.unescape(quote)   # RT 用 &#44; &#46; 等 HTML 实体，还原
 
    is_top = bool(critic.get("isTopCritic") or r.get("isTopReview"))
 
    return {
        "sentiment": r.get("scoreSentiment", ""),               # POSITIVE / NEGATIVE
        "date": r.get("createDate") or r.get("updateDate"),     # ISO 时间
        "score": r.get("originalScore", ""),                    # 如 "3.5/4"
        "is_top_critic": is_top,
        "critic": critic.get("displayName", ""),
        "publication": pub.get("name", ""),
        "quote": quote,
        "url": r.get("publicationReviewUrl", ""),
        "review_id": r.get("reviewId", ""),
    }
 
 
def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法: py -m scripts.rt_review_import_report <raw文件名> <movie_key>")
    in_arg, movie_key = sys.argv[1], sys.argv[2]
 
    in_path = in_arg if os.path.sep in in_arg or os.path.exists(in_arg) \
        else os.path.join(RAW_DIR, in_arg)
 
    try:
        with open(in_path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"找不到输入文件: {in_path}\n"
                         f"（把 F12 复制的内容存到 {RAW_DIR}/ 下）")
    except json.JSONDecodeError as e:
        raise SystemExit(f"输入不是合法 JSON: {e}\n"
                         "提示：F12 复制时确保复制的是完整的 JSON（数组或对象）。")
 
    raw_reviews = extract_reviews(raw)
    reviews = [convert_one(r) for r in raw_reviews]
 
    # 去重（按 review_id，防止分页复制时重复）
    seen = set()
    deduped = []
    for r in reviews:
        rid = r.get("review_id")
        if rid and rid in seen:
            continue
        if rid:
            seen.add(rid)
        deduped.append(r)
    reviews = deduped
 
    # 1. 输出标准格式 JSON → format/
    os.makedirs(FORMAT_DIR, exist_ok=True)
    format_path = os.path.join(FORMAT_DIR, f"{movie_key}.json")
    with open(format_path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
 
    fresh = sum(1 for r in reviews
                if "POSITIVE" in str(r["sentiment"]).upper() or "Fresh" in str(r["sentiment"]))
    header = (f"✓ 已转换 {len(reviews)} 条评论 → {format_path}\n"
              f"  fresh(好评): {fresh}  rotten(差评): {len(reviews)-fresh}  "
              f"→ 分数≈{round(fresh/len(reviews)*100) if reviews else 0}%")
 
    # 从 config 拿结算日 + 策略参数
    m_cfg = config.WATCHLIST.get(movie_key, {})
    settle = m_cfg.get("kalshi_settle_date")
 
    # 组装板块6所需：当前分数/n + config参数（支持单片覆盖）
    model_fn = None
    model_params = None
    rep_tmp = build_report(reviews)
    base_rate = m_cfg.get("base_rate")
    if base_rate is not None and rep_tmp.get("n_total", 0) > 0:
        params = config.get_strategy_params(movie_key)
 
        def model_fn(score, n, br, prior, drift, n_final, n_sims):
            inp = ModelInputs(score_now=score, n_now=n, base_rate=float(br),
                              prior_strength=prior, n_final=n_final, drift=drift)
            return run_model(inp, n_sims=n_sims).mean
 
        model_params = {
            "score_now": round(rep_tmp["tomatometer"]),   # 整数化，和模型口径一致
            "n_now": rep_tmp["n_total"],
            "base_rate": float(base_rate),
            "drift": params["DRIFT"], "prior_strength": params["PRIOR_STRENGTH"],
            "n_sims": params["N_SIMS"],
        }
 
    # 2+3. 生成报告：同时打印到终端 + 写入 report/ 的 txt
    os.makedirs(REPORT_DIR, exist_ok=True)
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    report_path = os.path.join(REPORT_DIR, f"{movie_key}_{today}.txt")
 
    with open(report_path, "w", encoding="utf-8") as fp:
        tee = Tee(sys.stdout, fp)
        old_stdout = sys.stdout
        sys.stdout = tee
        try:
            print(header + "\n")
            print(f"📋 === 报告 ({movie_key}) ===")
            print_report(build_report(reviews), settle_date=settle,
                         model_fn=model_fn, model_params=model_params)
        finally:
            sys.stdout = old_stdout
 
    print(f"\n✓ 报告已存 → {report_path}")
 
 
if __name__ == "__main__":
    main()