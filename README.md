# RT → Kalshi Edge Model　烂番茄 → Kalshi 边际模型

> Turn an early Rotten Tomatoes reading into a probability distribution over the
> **final** Tomatometer score at Kalshi settlement, then compute long (buy YES)
> and short (buy NO) edge against live market prices — and archive dated
> snapshots so the model can be backtested and calibrated over time.
>
> 把烂番茄解禁时的早期读数，变成"结算时刻最终分数"的概率分布，和 Kalshi
> 实时盘口比对算出做多/做空 edge；同时存档带日期的快照，让模型能被回测和校准。

---

## English

### What this is

This tool estimates where a movie's **final** Rotten Tomatoes score will land at
the Kalshi settlement time, using only what's visible at embargo-lift (current
score, review count, franchise history). It compares the model's fair value to
live Kalshi prices to surface positive-expected-value (edge) trades, and it
archives dated review + order-book snapshots that become the raw material for
backtesting.

**This is statistical edge trading, not arbitrage.** Every output is a
probability estimate, not a guarantee. The model can be wrong and the market may
know things the model doesn't. Treat each signal as "positive expected value *if*
the model is calibrated," never as a sure thing.

### The three commands

**1. Track an in-progress movie (reviews + order book):**
```
py -m scripts.fetch_reviews --movie toy_story_5
```
Scrapes all critic reviews, saves a dated snapshot to `data/snapshots/{movie}/`,
**also** grabs a Kalshi order-book snapshot to `data/orderbooks/{movie}/`
(the paired record is the gold-standard data for edge backtesting), prints a
quality report, and prints a ready-to-run analysis command.

**2. Pull a historical (settled) movie for backtesting:**
```
py -m scripts.fetch_historical --movie zootopia_2
```
Scrapes the full current set of reviews to `data/historical/{movie}_fullpull_{date}.json`.
Does **not** grab an order book (settled markets aren't available and historical
prices are gone). Used to calibrate the model, not to validate edge.

**3. Re-print a report from any saved JSON (no scraping):**
```
py -m scripts.show_report data/snapshots/toy_story_5/2026-06-21.json
```
Reads a saved review file and reprints the quality report. Works on both
snapshot and historical files.

**Then run the model:**
```
py -m scripts.run_analysis --movie toy_story_5 --score 93 --reviews 210 --live
```
Runs the Bayesian + Monte Carlo model, pulls live prices (`--live`), prints
long/short edge tables and robust + best-value picks.

### run_analysis options

- `--movie` (required) a key in `config.WATCHLIST`
- `--score` (required) the RT % you see now
- `--reviews` (required) how many critic reviews that % is based on
- `--side` `long`, `short`, or `both` (default `both`)
- `--live` pull live prices from Kalshi (omit to use the manual ladder)
- `--drift` / `--base-rate` / `--prior` / `--nfinal` temporarily override a model
  parameter without editing config. Given → used; omitted → config value is used.
  Overrides are echoed in the output header.

### The quality report (4 sections)

Printed by `fetch_reviews`, `fetch_historical`, and `show_report`:

1. **Overview** — total, fresh/rotten, current Tomatometer.
2. **Critic tier** — Top critics vs others. A big gap (top critics harsher) is a
   fragility signal: influential voices are less sold than the headline suggests.
3. **Score quality** — using official 10-point and letter + 5-star + 4-star
   conversions: mean, median, **borderline-fresh** (fresh reviews scoring 6.0–7.0,
   most likely to flip), severe-rotten (< 5.0), and a distribution chart.
4. **Time trends** (share one date axis): Tomatometer (cumulative), mean score
   (cumulative), rotten% (per-day). Cumulative shows how the score converged;
   per-day rotten% is the sensitive early-warning for a turning tide.

### Adding a movie

Copy a block in `config.py`'s `WATCHLIST`, rename the key, fill it in. Three
fields require a manual lookup and **must be correct** (the rest are model
parameters you can placeholder while just collecting data):

- `kalshi_event` — Kalshi event ticker (e.g. `KXRT-TOY`). **Naming is
  inconsistent** (`KXRT-TOY` vs `KXRTZOOTOPIA2`), so confirm each one on the
  Kalshi site rather than guessing.
- `kalshi_settle_date` — settlement date as `YYYY-MM-DD`. Kalshi settles movie
  contracts the first Monday after wide release, 10:00 ET. Read it off the
  market's close time on the Kalshi site. (Settled markets aren't in the API, so
  for historical movies you must read this from the website.)
- `rt_movie_id` — Rotten Tomatoes internal UUID. On the RT reviews page: F12 →
  Network → Fetch/XHR → find the `reviews` request; the UUID is in its URL.

### Tests

```
py -m pytest -q
```

### Honest limitations

- The model assumes reviews are **independent and identically distributed**. Real
  reviews herd, so it likely **underestimates tail risk** (a score collapse).
- `drift` and `prior_strength` are hand-set, not yet calibrated from data.
- Backtesting infrastructure is being built; until then the model's probabilities
  are **not yet validated**, and a model-vs-market gap is not proven edge.

---

## 中文

### 这是什么

这个工具用解禁时能拿到的信息（当前分数、评论数、系列历史），估算电影在 Kalshi
结算时刻的**最终**烂番茄分数，和 Kalshi 实时价比对找出正期望值（edge）交易；
同时存档带日期的评论 + 盘口快照，作为回测的原料。

**这是统计 edge 交易，不是无风险套利。** 所有输出都是概率估计，不是保证。模型
可能错，市场可能知道模型不知道的事。把每个信号当成"如果模型校准良好则正期望"，
绝不当成稳赢。

### 三条命令

**1. 追踪正在进行的片（评论 + 盘口）：**
```
py -m scripts.fetch_reviews --movie toy_story_5
```
抓全部影评人评论，存带日期的快照到 `data/snapshots/{片}/`，**并顺手**抓一份
Kalshi 盘口快照到 `data/orderbooks/{片}/`（这一对配对数据是 edge 回测的金标准），
打印质量报告，再打印一行可直接运行的分析命令。

**2. 抓历史（已结算）片做回测：**
```
py -m scripts.fetch_historical --movie zootopia_2
```
抓当前全量评论到 `data/historical/{片}_fullpull_{日期}.json`。**不抓盘口**（已结算
市场拉不到，历史盘口也早没了）。用于校准模型，不用于验证 edge。

**3. 从任意已存 JSON 重看报告（不联网）：**
```
py -m scripts.show_report data/snapshots/toy_story_5/2026-06-21.json
```
读一个已存评论文件，重新打印质量报告。snapshot 和 historical 文件都能读。

**然后跑模型：**
```
py -m scripts.run_analysis --movie toy_story_5 --score 93 --reviews 210 --live
```
跑贝叶斯 + 蒙特卡洛模型，拉实时价（`--live`），打印做多/做空 edge 表和推荐。

### run_analysis 参数

- `--movie`（必填）config.WATCHLIST 里的 key
- `--score`（必填）此刻看到的 RT 分数 %
- `--reviews`（必填）这个分数基于多少条影评
- `--side` `long` / `short` / `both`（默认 both）
- `--live` 从 Kalshi 拉实时价（不加则用手填 ladder）
- `--drift` / `--base-rate` / `--prior` / `--nfinal` 不改 config 临时覆盖某参数。
  命令行给了就用、没给就用 config。覆盖了什么会在输出顶部提示。

### 质量报告（四板块）

由 `fetch_reviews`、`fetch_historical`、`show_report` 共同打印：

1. **总览** —— 总数、好评/差评、当前新鲜度。
2. **影评人级别** —— 顶级影评人 vs 普通。差距大（顶级更挑剔）是脆弱信号：有
   影响力的人比表面分数更不买账。
3. **打分质量** —— 用官方 10 分制、字母制、5 星制、4 星制换算：平均、中位、
   **脆弱好评**（换算分 6.0~7.0 的好评，最易翻盘）、严重差评（<5.0）、分布图。
4. **时间趋势合辑**（共用一套日期轴）：新鲜度（累计）、平均分（累计）、差评%
   （每天独立）。累计看分数怎么收敛；每天独立的差评%是口碑转向的灵敏预警。

### 加一部电影

复制 `config.py` 里 `WATCHLIST` 的一块，改 key、填值。三个字段要手动查、且
**必须准**（其余是模型参数，只抓数据时可先占位）：

- `kalshi_event` —— Kalshi event ticker（如 `KXRT-TOY`）。**命名不统一**
  （`KXRT-TOY` vs `KXRTZOOTOPIA2`），所以每个都去 Kalshi 网站确认，别猜。
- `kalshi_settle_date` —— 结算日，填 `YYYY-MM-DD`。Kalshi 电影合约在全美公映后
  第一个周一 10:00 ET 结算。从 Kalshi 市场页的 close time 读。（已结算市场不在
  API 里，所以历史片这个必须从网站查。）
- `rt_movie_id` —— 烂番茄内部 UUID。RT 评论页 F12 → 网络 → Fetch/XHR → 找
  `reviews` 请求，UUID 在它 URL 里。

### 测试

```
py -m pytest -q
```

### 诚实的局限

- 模型假设评论**独立同分布**。真实评论会扎堆（羊群效应），所以很可能**低估尾部
  风险**（口碑崩盘）。
- `drift` 和 `prior_strength` 目前手工设，没用数据校准。
- 回测框架还在搭。在那之前，模型的概率**尚未被验证**，模型与市场的分歧不等于
  已证实的 edge。

---

## Architecture　项目分层

```
rt-kalshi/
├── src/                          # 能力模块（被调用）/ capability modules
│   ├── config.py                 # 全局设置 + 电影清单 / settings + watchlist
│   ├── model/
│   │   └── bayesian.py           # Beta 后验 + 蒙特卡洛（纯数学，不联网）
│   ├── strategy/
│   │   └── decide.py             # 概率 + 价格 → edge → 推荐
│   ├── collectors/               # 采集层（联网、获取数据）/ data acquisition
│   │   ├── kalshi_client.py      # 抓价格 + 盘口快照 / prices + order-book snapshots
│   │   └── rt_reviews.py         # 抓评论 + 存快照/历史 / reviews + snapshot/historical save
│   └── analysis/                 # 分析层（不联网、不算概率）/ analysis only
│       └── reviews.py            # 评论质量报告（四板块）/ quality report
├── scripts/                      # 命令入口（你直接 py -m 运行）/ entry points
│   ├── run_analysis.py           # 跑模型出 edge
│   ├── fetch_reviews.py          # 抓正在进行的片：评论 + 盘口 → snapshots/orderbooks
│   ├── fetch_historical.py       # 抓历史片：只评论 → historical
│   └── show_report.py            # 读任意已存 JSON 重出报告（不联网）
├── tests/
│   └── test_model.py
├── data/                         # 原始存档「只进不删」+ 派生表
│   ├── snapshots/{片}/{日期}.json      # 每日评论快照（金标准）
│   ├── orderbooks/{片}/{日期}.json     # 每日盘口快照（金标准，与评论配对）
│   ├── historical/{片}_fullpull_{日期}.json  # 历史片全量（切片重建，有误差）
│   └── backtest/samples.csv            # 派生回测表（可重新生成）
├── requirements.txt
└── README.md
```

### Layering principle　分层原则

`src/` holds **capabilities** (things that get called: math, scrapers,
analysis). `scripts/` holds **entry points** (the commands you type — thin:
parse args, call capabilities, print). Within `src/`, dependencies flow one way,
so any layer can be swapped without touching the others.

`src/` 装**能力**（被调用的：数学、采集、分析）。`scripts/` 装**入口**（你敲的
命令——很薄：解析参数、调用能力、打印）。`src/` 内部单向依赖，换任何一层不影响
其它层。

```
collectors (抓数据) → analysis / model (加工) → strategy (出 edge) → scripts (打印)
```

For example `model/bayesian.py` is pure math with no network, so it's unit-
tested in isolation and reused unchanged by the coming backtest module.

例如 `model/bayesian.py` 是纯数学、不联网，能单独测试，也能被将来的回测模块原样
复用。

### Data discipline　数据纪律

Two classes of data, **physically separated** so backtests never confuse them:

两类数据，**物理隔离**，回测时永不混淆：

- **Gold standard** — daily `snapshots/` + `orderbooks/` of in-progress movies.
  Records what the market actually saw each day. The **only** data that can
  validate edge. Start collecting early; it grows over time.
  **金标准** —— 正在进行的片的每日 `snapshots/` + `orderbooks/`。记录市场每天
  真实看到的状态。**唯一**能验证 edge 的数据。尽早开始攒，随时间生长。

- **Reconstructed** — `historical/` full pulls of settled movies. Sliced by each
  review's `createDate` to rebuild past states. Has small error (reviews can be
  re-judged after the fact while createDate stays put), so it calibrates the
  model but can't validate edge (historical prices are gone).
  **重建** —— 已结算片的 `historical/` 全量。靠每条评论的 `createDate` 切片重建
  历史状态。有小误差（评论可能被事后改判而 createDate 不变），所以只能校准模型、
  不能验证 edge（历史盘口拿不到了）。

**Rules:** raw archives are append-only (never overwrite/delete); `samples.csv`
is derived and regenerable; cross-day keeps a new file, same-day overwrites.

**铁律：** 原始存档只进不删（不覆盖/不删除）；`samples.csv` 是派生的、可重新
生成；跨天保留新文件，同天覆盖。

---

*Statistical estimate, not a guarantee. Not financial advice.*
*统计估计，不是保证，更不是投资建议。*