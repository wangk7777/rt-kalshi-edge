"""
验证：小众历史片（最终 n<100）在 n=N_AT 时，模型预测最终分 vs 真实最终分。
回答：小众片能不能在早期（n=N_AT）就交易（分数是否已稳定、可预测）。
排除 config 里 exclude_from_backtest=True 的片。

USE_FIXED_NFINAL 开关：
  True  → 用 FIXED_NFINAL_GUESS（模拟实盘：你不知道真实n，统一猜一个值）
  False → 用真实 total_n（上帝视角：假设完美预知最终评论数，看模型上限）

用法：py temporary_script_debug_paging.py
"""
import json
import os
from datetime import datetime, timezone
from src import config
from src.model.bayesian import ModelInputs, run_model

HIST_DIR = os.path.join("data", "historical")
N_AT = 40                    # 在 n=N_AT 时预测（改这一个值即可）
NICHE_MAX_NFINAL = 100       # 只看最终评论数 <100 的小众片

# ---- n_final 模式开关 ----
USE_FIXED_NFINAL = True       # True=用猜测值(模拟实盘), False=用真实n_final(上帝视角)
FIXED_NFINAL_GUESS = 60       # USE_FIXED_NFINAL=True 时用这个

# 策略参数（用你当前的默认）
_p = config.get_strategy_params()
PRIOR = _p["PRIOR_STRENGTH"]
DRIFT = _p["DRIFT"]
N_SIMS = _p["N_SIMS"]


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
    skipped_excluded = 0
    skipped_not_niche = 0
    skipped_few = 0

    for movie_key, m in config.WATCHLIST.items():
        if m.get("exclude_from_backtest") is True:
            skipped_excluded += 1
            continue

        base_rate = m.get("base_rate")
        final_official = m.get("final_score_official")
        if base_rate is None or final_official is None:
            continue

        path = os.path.join(HIST_DIR, f"{movie_key}_fullpull.json")
        if not os.path.exists(path):
            continue
        reviews = json.load(open(path, encoding="utf-8"))
        dated = sorted(
            [(parse_date(r.get("date")), is_fresh(r)) for r in reviews if parse_date(r.get("date"))],
            key=lambda x: x[0])
        total_n = len(dated)

        if total_n >= NICHE_MAX_NFINAL:
            skipped_not_niche += 1
            continue
        if total_n < N_AT:
            skipped_few += 1
            continue

        # n=N_AT 时的分数（整数化，和实盘/模型口径一致）
        first_slice = dated[:N_AT]
        fresh_at = sum(1 for _, fr in first_slice if fr)
        score_at = round(fresh_at / N_AT * 100)

        # ★ n_final 按开关选 ★
        if USE_FIXED_NFINAL:
            n_final_used = max(FIXED_NFINAL_GUESS, N_AT)
        else:
            n_final_used = max(total_n, N_AT)

        inp = ModelInputs(score_now=score_at, n_now=N_AT, base_rate=float(base_rate),
                          prior_strength=PRIOR, n_final=n_final_used, drift=DRIFT)
        res = run_model(inp, n_sims=N_SIMS)
        pred_final = res.mean
        real_final = float(final_official)
        error = pred_final - real_final

        rows.append({
            "movie": movie_key, "final_n": total_n, "nfinal_used": n_final_used,
            "score_at": score_at, "pred": pred_final, "real": real_final, "error": error,
        })

    if not rows:
        print("没有符合条件的小众片")
        print(f"(排除: exclude={skipped_excluded}, 非小众={skipped_not_niche}, 不足{N_AT}={skipped_few})")
        return

    mode = (f"固定n_final={FIXED_NFINAL_GUESS}(模拟实盘)" if USE_FIXED_NFINAL
            else "真实n_final(上帝视角)")
    print(f"预测时点: n={N_AT}   n_final模式: {mode}")
    print(f"{'电影':32}{'最终n':>6}{'用的nf':>7}{f'n={N_AT}分':>7}{'预测':>7}{'真实':>7}{'误差':>7}")
    print("-" * 76)
    for r in sorted(rows, key=lambda x: x["error"]):
        print(f"{r['movie'][:30]:32}{r['final_n']:>6}{r['nfinal_used']:>7}"
              f"{r['score_at']:>7.0f}{r['pred']:>7.1f}{r['real']:>7.0f}{r['error']:>+7.1f}")

    errors = [r["error"] for r in rows]
    abs_errors = [abs(e) for e in errors]
    print("-" * 76)
    print(f"小众片数(最终n<{NICHE_MAX_NFINAL}): {len(rows)}   预测时点n={N_AT}   {mode}")
    print(f"  (排除: exclude={skipped_excluded}, 非小众={skipped_not_niche}, 不足{N_AT}={skipped_few})")
    print(f"平均误差(带符号): {sum(errors)/len(errors):+.2f} (正=高估)")
    print(f"平均绝对误差: {sum(abs_errors)/len(abs_errors):.2f}")
    print(f"高估: {sum(1 for e in errors if e>0)}  低估: {sum(1 for e in errors if e<0)}")
    within3 = sum(1 for e in abs_errors if e <= 3)
    within5 = sum(1 for e in abs_errors if e <= 5)
    print(f"误差≤3分: {within3}/{len(rows)} ({within3*100//len(rows)}%)")
    print(f"误差≤5分: {within5}/{len(rows)} ({within5*100//len(rows)}%)")


if __name__ == "__main__":
    main()