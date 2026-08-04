"""
命令行入口：给一部电影跑模型，打印做多/做空的 edge 表和推荐。

用法示例（在项目根目录运行）：
    py -m scripts.archive_old.run_analysis --movie toy_story_5 --score 96 --reviews 45
    py -m scripts.archive_old.run_analysis --movie toy_story_5 --score 96 --reviews 45 --side short
    py -m scripts.archive_old.run_analysis --movie toy_story_5 --score 96 --reviews 45 --drift 4

现阶段烂番茄分数和评论数要手动传入（或先跑 fetch_reviews 拿到）。
模型参数(drift/base_rate/prior/n_final)可用命令行临时覆盖，不给就用 config 里的。
Kalshi 价格来自每部电影自己的 ladder（加 --live 拉实时价）。
"""

from __future__ import annotations

# argparse 是 Python 标准库，用来解析命令行参数（--movie 这些）
import argparse

# 导入我们自己写的各个模块
from src import config
from src.collectors.kalshi_client import get_ladder_manual
from src.model.bayesian import ModelInputs, run_model
from src.strategy.decide import choose, evaluate_ladder
from src.config import DEFAULT_DRIFT, DEFAULT_PRIOR_STRENGTH

# ---- 终端彩色文字的小工具（这些是 ANSI 转义码，不用 numpy/库）----
# \033[32m 表示绿色，\033[0m 表示恢复默认。包住一段文字就能上色。
GREEN, RED, DIM, BOLD, END = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def color_edge(edge: float, min_edge: float) -> str:
    """根据 edge 大小给它上色：达标绿色、负数红色、其它灰色。"""
    c = GREEN if edge >= min_edge else (RED if edge < 0 else DIM)
    sign = "+" if edge > 0 else ""   # 正数前面加个 + 号好看
    return f"{c}{sign}{edge:.0f}{END}"   # f"..." 是 f-string，{} 里能直接塞变量


def print_table(evals, side, min_edge):
    """打印一张表格：每一档的价格、公平价、胜率、edge。side 是 'long' 或 'short'。"""
    is_long = side == "long"
    head = "Above" if is_long else "Below"   # 做多看"高于"，做空看"低于"
    pcol = "YES" if is_long else "NO"
    # 表头。:>5 这种是格式化对齐：>右对齐、数字是宽度。
    print(f"\n  {head:<6} {pcol:>5} {'Fair':>6} {'Win%':>6} {'Edge':>8}")
    print("  " + "-" * 36)   # "-" * 36 = 36 个横线，画分隔线
    for e in evals:          # 遍历每一档
        # 根据做多还是做空，取对应那一侧的数字
        if is_long:
            price, fair, win, edge = e.yes_price, e.fair_yes, e.p_yes, e.edge_yes
        else:
            price, fair, win, edge = e.no_price, e.fair_no, e.p_no, e.edge_no
        print(
            f"  {e.t:<6.0f} {price:>5.0f} {fair:>6.0f} "
            f"{win*100:>5.0f}% {color_edge(edge, min_edge):>16}"
        )


def print_pick(label, pick, side):
    """打印一条推荐。pick 为 None 时表示这边没机会。"""
    if pick is None:
        print(f"  {BOLD}{label}:{END} 没有合约达标，放弃这一边。")
        return
    is_long = side == "long"
    verb = "Buy YES above" if is_long else "Buy NO above"
    # 根据做多/做空取对应字段
    win = pick.p_yes if is_long else pick.p_no
    fair = pick.fair_yes if is_long else pick.fair_no
    mkt = pick.yes_price if is_long else pick.no_price
    edge = pick.edge_yes if is_long else pick.edge_no
    print(
        f"  {BOLD}{label}:{END} {verb} {pick.t:.0f}%  "
        f"(胜率 {win*100:.0f}%, 公平价 {fair:.0f}c, 市价 {mkt:.0f}c, "
        f"{GREEN}+{edge:.0f}c edge{END})"
    )


def main():
    """主函数：解析参数 → 跑模型 → 打印结果。"""
    # 设置命令行参数解析器
    ap = argparse.ArgumentParser(description="RT -> Kalshi edge model")
    ap.add_argument("--movie", required=True, help="config.WATCHLIST 里的 key")
    ap.add_argument("--score", type=float, required=True, help="此刻显示的 RT 分数 %")
    ap.add_argument("--reviews", type=int, required=True, help="此刻的评论数")
    ap.add_argument("--side", choices=["long", "short", "both"], default="both")
    ap.add_argument("--live", action="store_true", help="从 Kalshi 拉实时价格")
    # ---- 可选覆盖参数：给了就用命令行的，没给(None)就用 config 里的 ----
    # 方便临时做实验（比如试不同 drift），不用改 config 文件。
    ap.add_argument("--drift", type=float, default=None, help="临时覆盖 drift")
    ap.add_argument("--base-rate", type=float, default=None, help="临时覆盖 base_rate")
    ap.add_argument("--prior", type=float, default=None, help="临时覆盖 prior_strength")
    ap.add_argument("--nfinal", type=int, default=None, help="临时覆盖 n_final")
    args = ap.parse_args()   # 真正去读你敲的命令，把值存进 args

    # 检查这部电影在不在清单里。不在就报错退出。
    if args.movie not in config.WATCHLIST:
        raise SystemExit(f"未知电影 '{args.movie}'。请先加到 config.WATCHLIST。")
    m = config.WATCHLIST[args.movie]   # 取出这部片的参数字典

    # 解析最终用哪个值：命令行给了(不是 None)就用命令行，否则用 config。
    # "A if 条件 else B" 是三元表达式：条件成立取 A，否则取 B。
    base_rate = args.base_rate if args.base_rate is not None else m["base_rate"]
    prior_strength = args.prior if args.prior is not None else m.get("prior_strength", DEFAULT_PRIOR_STRENGTH)
    n_final = args.nfinal if args.nfinal is not None else m["n_final"]
    drift = args.drift if args.drift is not None else m.get("drift", DEFAULT_DRIFT)

    # 把所有输入打包成 ModelInputs 对象
    inputs = ModelInputs(
        score_now=args.score,
        n_now=args.reviews,
        base_rate=base_rate,
        prior_strength=prior_strength,
        n_final=n_final,
        drift=drift,
    )
    result = run_model(inputs)   # 跑模型，得到终值分布

    # 取这部电影自己的 ladder；如果它没写 ladder，就退回用 DEFAULT_LADDER。
    # m.get("ladder", 默认值) 的意思是"有 ladder 就用它，没有就用默认值"，不会报错。
    # --live 就拉实时价；否则用 config 里手填的价
    if args.live:
        from src.collectors.kalshi_client import get_ladder_live
        ladder = get_ladder_live(m["kalshi_event"])
        print(f"  (已拉取 {len(ladder)} 档实时价格)")
    else:
        ladder_rows = m.get("ladder", config.DEFAULT_LADDER)
        ladder = get_ladder_manual(ladder_rows)

    evals = evaluate_ladder(result, ladder)   # 每档打分
    picks = choose(evals, min_edge=config.MIN_EDGE, win_floor=config.WIN_FLOOR)  # 选推荐

    # ---- 打印结果 ----
    print(f"\n{BOLD}{m['title']}{END}  —  {args.score:.0f}% on {args.reviews} reviews")
    # 如果用了临时覆盖参数，提示一下，免得忘了自己改过
    overrides = []
    if args.drift is not None: overrides.append(f"drift={drift}")
    if args.base_rate is not None: overrides.append(f"base_rate={base_rate}")
    if args.prior is not None: overrides.append(f"prior={prior_strength}")
    if args.nfinal is not None: overrides.append(f"n_final={n_final}")
    if overrides:
        print(f"  {DIM}[临时覆盖: {', '.join(overrides)}]{END}")
    print(f"  模型预估终值: {BOLD}{result.mean:.1f}%{END} "
          f"(+/- {result.sd:.1f} 点, 1 sigma)")

    # args.side 是 long/short/both，决定打印哪边
    if args.side in ("long", "both"):
        print(f"\n{BOLD}LONG 做多 (买 YES / above){END}")
        print_table(evals, "long", config.MIN_EDGE)
        print()
        print_pick("最稳健做多", picks.robust_long, "long")
        print_pick("最佳价值做多", picks.best_long, "long")

    if args.side in ("short", "both"):
        print(f"\n{BOLD}SHORT 做空 (买 NO / below){END}")
        print_table(evals, "short", config.MIN_EDGE)
        print()
        print_pick("最稳健做空", picks.robust_short, "short")
        print_pick("最佳价值做空", picks.best_short, "short")

    print(f"\n{DIM}这是统计估计，不是保证，更不是投资建议。{END}\n")


# 这行的意思是：只有"直接运行这个文件"时才执行 main()。
# 如果这个文件是被别的文件 import 的，就不会自动跑。这是 Python 的标准写法。
if __name__ == "__main__":
    main()