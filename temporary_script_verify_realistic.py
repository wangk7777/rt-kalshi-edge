"""
验证：模拟真实交易环境——只测"n能到80、且n=80时还没结算"的片。
排除：评论永远到不了80的小众片、n=80时已过结算日的片。
这样验证的是你实盘真正会出手的场景。

用法：py verify_realistic.py
"""
import json
import os
from datetime import datetime, timezone
from src import config
from src.model.bayesian import ModelInputs, run_model

HIST_DIR = os.path.join("data", "historical")
N_AT = 80
N_FINAL = 200
PRIOR = 20.0
DRIFT = 1.0
EXCLUDE_2026 = False   # 保持holdout干净：排除2026片


def is_fresh(r):
    s = str(r.get("sentiment", ""))
    return "Fresh" in s or s.upper() == "POSITIVE"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def main():
    rows = []
    skipped_few = 0        # 评论不够80
    skipped_late = 0       # n=80时已过结算日
    skipped_2026 = 0

    for movie_key, m in config.WATCHLIST.items():
        base_rate = m.get("base_rate")
        final_official = m.get("final_score_official")
        settle = m.get("kalshi_settle_date", "")
        if base_rate is None or final_official is None:
            continue

        # 排除2026 holdout
        settle_dt = parse_date(settle if "T" in str(settle) else str(settle) + "T14:00:00Z")
        if EXCLUDE_2026 and settle_dt and settle_dt.year == 2026:
            skipped_2026 += 1
            continue

        path = os.path.join(HIST_DIR, f"{movie_key}_fullpull.json")
        if not os.path.exists(path):
            continue
        reviews = json.load(open(path, encoding="utf-8"))
        dated = sorted(
            [(parse_date(r.get("date")), is_fresh(r)) for r in reviews if parse_date(r.get("date"))],
            key=lambda x: x[0])

        # 条件1：评论总数要到80（实盘才会交易）
        if len(dated) < N_AT:
            skipped_few += 1
            continue

        # 条件2：第80条评论的日期，要在结算日之前（n=80时还有交易窗口）
        date_at_80 = dated[N_AT - 1][0]   # 第80条评论的日期
        if settle_dt and date_at_80 and date_at_80 > settle_dt:
            skipped_late += 1
            continue   # n=80时已过结算日，实盘没法交易

        # n=80时的分数
        first80 = dated[:N_AT]
        fresh80 = sum(1 for _, fr in first80 if fr)
        score_80 = round(fresh80 / N_AT * 100, 2)

        # 模型预测
        inp = ModelInputs(score_now=score_80, n_now=N_AT, base_rate=float(base_rate),
                          prior_strength=PRIOR, n_final=N_FINAL, drift=DRIFT)
        res = run_model(inp, n_sims=50000)
        pred_final = res.mean
        real_final = float(final_official)
        error = pred_final - real_final

        rows.append({
            "movie": movie_key, "score_80": score_80, "date_80": date_at_80,
            "settle": settle_dt, "pred": pred_final, "real": real_final, "error": error,
        })

    if not rows:
        print("没有符合条件的片")
        return

    print(f"{'电影':32}{'n=80分':>7}{'预测':>7}{'真实':>7}{'误差':>7}")
    print("-" * 62)
    for r in sorted(rows, key=lambda x: x["error"]):
        print(f"{r['movie'][:30]:32}{r['score_80']:>7.0f}{r['pred']:>7.1f}"
              f"{r['real']:>7.0f}{r['error']:>+7.1f}")

    errors = [r["error"] for r in rows]
    abs_errors = [abs(e) for e in errors]
    print("-" * 62)
    print(f"符合真实交易条件的片: {len(rows)}")
    print(f"  (排除: 评论不够80={skipped_few}, n=80时已过结算={skipped_late}, "
          f"2026holdout={skipped_2026})")
    print(f"平均误差(带符号): {sum(errors)/len(errors):+.2f} (正=高估最终分)")
    print(f"平均绝对误差: {sum(abs_errors)/len(abs_errors):.2f}")
    print(f"高估: {sum(1 for e in errors if e>0)}  低估: {sum(1 for e in errors if e<0)}")
    within3 = sum(1 for e in abs_errors if e <= 3)
    within5 = sum(1 for e in abs_errors if e <= 5)
    print(f"误差≤3分: {within3}/{len(rows)} ({within3*100//len(rows)}%)")
    print(f"误差≤5分: {within5}/{len(rows)} ({within5*100//len(rows)}%)")


if __name__ == "__main__":
    main()