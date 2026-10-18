# RT → Kalshi / Polymarket Edge Model　烂番茄 → 预测市场边际模型

> Turn an early Rotten Tomatoes reading into a probability distribution over the
> **final** Tomatometer score at settlement, then compute long (buy YES) and
> short (buy NO) edge against live prices — on **both Kalshi and Polymarket**,
> through a shared platform-adapter layer, with a calibrated model and a
> realistic order-book backtest behind every number.
>
> 把烂番茄解禁时的早期读数，变成"结算时刻最终分数"的概率分布，和 **Kalshi、
> Polymarket** 的实时盘口比对算出做多/做空 edge；两个平台共用一套适配层，模型经过
> 校准、每个数字背后都有真实盘口的逐档回测支撑。

---

## English

### What this is

This tool estimates where a movie's **final** Rotten Tomatoes score will land at
settlement, using only what's visible early (current score, review count,
franchise/director history). It compares the model's fair value to live market
prices to surface positive-expected-value (edge) trades, and supports two
venues — Kalshi and Polymarket — behind one interface.

**This is statistical edge trading, not arbitrage.** Every output is a
probability estimate, not a guarantee. The model can be wrong and the market may
know things the model doesn't. Treat each signal as "positive expected value
*if* the model is calibrated," never as a sure thing.

### The core idea: late-review gravity

Across 147 historical movies, Tomatometer scores drift **down** from the early
embargo reading toward settlement — early reviews skew optimistic, and a second
wave around wide release pulls the number lower. When review count is large
enough that the market has over- or under-priced this drift, there's edge in
taking the mispriced side. The Bayesian model encodes this with a `drift`
parameter and a franchise/director `base_rate` prior; Monte Carlo turns the two
into a full distribution over the final score.

### Model status (calibrated, this is the production baseline)

Parameters are chosen on a held-out **validation** split by **calibration error,
never by PnL** — the single most important discipline in this project. The
current baseline is **`drift=1, prior_strength=20`** (`config.STRATEGY_DEFAULTS`):

- Validation calibration error **0.0083**, 2026 out-of-sample **0.0146** — the
  calibration curve tracks the diagonal across all probability buckets.
- Predicting the final score at n=80, mean absolute error **2.85 points**,
  84% of movies within 5 points, no systematic bias (+0.44).

A note on `drift`: it has shifted (4 → 2 → 1) every time a scoring-convention bug
was fixed. The lesson, recorded in `CLAUDE.md`, is that **an "off" parameter is
usually the symptom of a convention mismatch elsewhere — fix the convention,
re-run calibration, and the parameter moves toward its true value.** All model
inputs and outputs are now integer-rounded to match how RT, Kalshi and
Polymarket all report and settle on integer Tomatometer scores.

### The two platforms (and why they can't share a single switch)

| | Kalshi | Polymarket |
|---|---|---|
| Find market | `kalshi_event` ticker | `polymarket_event_slug` |
| Rungs | dense ladder, `above X` | sparse buckets (60/70/80/90+) |
| Settlement rule | **strictly greater** (`> X`) | **at least** (`≥ X`) |
| YES probability | `prob_at_least(floor + 1)` | `prob_at_least(floor)` |
| Order book | YES bids only (NO derived) | **two independent tokens**, each with its own book |
| Price unit | integer cents | 0–1 decimal strings (×100) |
| Settle time | 14:00 UTC | 10:00 AM ET |
| Auth to read | none | none |

These differences run deep — a one-off boolean switch would scatter `if
polymarket:` across the codebase. Instead every platform-specific rule is
sealed inside a **platform adapter** (`src/collectors/platforms/`), so `monitor`
and the report talk to a uniform interface and don't know which venue they're
looking at. The core model (the final-score distribution) is **platform-neutral
and reused unchanged**; only *how the distribution is used* differs
(`prob_at_least(floor)` vs `floor+1`).

### The main command: live monitoring

```
py -m scripts.monitor
```

A config-driven loop that, every 15 minutes, pulls each watched movie's live RT
score, runs the model once, and checks every rung on every active platform for
a tradeable edge. Top-of-file switches:

- `PLATFORM_MODE` — `"kalshi"`, `"polymarket"`, or `"both"`. Combined with the
  fields each movie fills in `config` (two-layer filter: *opened on* ∩ *mode*),
  this decides what's watched. Set `"polymarket"` after moving off Kalshi and
  every movie is viewed only on Polymarket.
- `COMPACT_MODE` — `False` (default) prints every rung's prob / price / edge,
  flagging the ones with an opportunity with a `★`; `True` prints only the `★`
  rows.

Output marks each opportunity with its platform and the exact threshold meaning
(`[kalshi] ≥81` vs `[polymarket] ≥80`), the model win-probability, the edge, and
the real fill cost after walking the book for the intended size.

### Review collection (how RT data gets in)

RT's full-review API is behind Akamai, so there are two paths:

1. **`monitor` live score** — `src/collectors/rt_summary.py` reads the current
   score + review count from the movie page's JSON-LD (BeautifulSoup). This is
   what the loop polls automatically. It parses the page defensively: it skips
   non-`Movie` JSON-LD blocks to find the real title (a bug that once pulled a
   same-named older film), and returns `None` rather than a wrong number on a
   truncated or malformed page.

2. **Full reviews, manually** — paste a short JavaScript snippet into the RT
   page's F12 Console. Running in the real browser (with its cookies and
   Akamai clearance) it auto-paginates all critic reviews (the `after` cursor is
   just the base64 of the page index), and downloads a JSON file. Drop that into
   `data/new_rt_review_data/raw/` and run:

   ```
   py -m scripts.rt_review_import_report <raw_file.json> <movie_key>
   ```

   It converts RT's raw format to the project format into `format/`, and writes
   a dated quality report to `report/`.

### The quality report

Printed by `rt_review_import_report`:

1. **Overview** — total, fresh/rotten, current Tomatometer.
2. **Critic tier** — top critics vs others; a gap (top critics harsher) is a
   fragility signal.
3. **Score quality** — official 10-point / letter / 5-star / 4-star conversions:
   mean, median, borderline-fresh (6.0–7.0, most likely to flip), severe-rotten.
4. **Time trends** — Tomatometer (cumulative), mean score (cumulative), and
   **rotten count per day** (absolute counts, not small-sample percentages, so
   one stray rotten review no longer reads as "turning tide").
5. **Growth forecast** — daily new reviews, overall and recent-3-day pace, and
   four `n_final` estimates (hold / linear-recent / linear-overall / decay) using
   days-to-settlement from today. **Used to set each movie's `n_final`.** Note
   the blind spot: it extrapolates the pre-release lull, so for a movie settling
   after wide release, bump `n_final` up for the second review wave.
6. **Model predictions** — runs the model at each of the four forecast `n_final`
   values, so you can see how sensitive the predicted score (hence the trade) is
   to the review-count guess.

### Adding a movie

Copy a block in `config.py`'s `WATCHLIST`, rename the key, fill it in. Fields
that need a manual lookup and **must be correct**:

- `base_rate` — franchise / director historical average (see the base-rate
  guide in the project docs).
- `rt_movie_id` — RT internal UUID. On the RT page: Ctrl+U → search `emsId`.
- Kalshi movies: `kalshi_event` (ticker — **naming is inconsistent**, confirm on
  site) and `kalshi_settle_date`.
- Polymarket movies: `polymarket_event_slug` (the part after `/event/` in the
  URL) and `polymarket_settle_date`.
- Fill both platforms' fields if the movie is open on both.
- `n_final` can start at the default 200 and be refined from the growth forecast
  once reviews are in.
- `embargo_date` optional (monitor filters by settle date vs today anyway).

### Tests

```
py -m pytest -q
```

`tests/test_monitor.py` covers the pure logic in isolation — fill/cost math,
opportunity thresholds, the two-layer platform filter, the Kalshi-vs-Polymarket
rule difference, and defensive parsing of malformed RT pages. (One of these
tests is what surfaced the JSON-LD same-name-movie bug.)

### Honest limitations

- The model assumes reviews are **i.i.d.**; real reviews herd, so it likely
  **underestimates tail risk** (a score collapse).
- **No live trade has been placed yet.** The system monitors and identifies
  opportunities in real time; the ~28% figure seen in reports is **backtest**
  PnL, held-to-settlement, not realized trading. Kalshi has a hard China-
  compliance constraint, which is the reason for the Polymarket migration.
- Polymarket's RT markets are currently **thin** (wide spreads, small size), so
  a model-vs-price gap there may not be capturable after slippage.
- `n_final` is guessed in production; the growth forecast narrows the guess but
  can't eliminate it, and niche films are hardest to pin down.

---

## 中文

### 这是什么

这个工具用早期能拿到的信息（当前分数、评论数、系列/导演历史），估算电影在结算时刻
的**最终**烂番茄分数，和实时市场价比对找出正期望值（edge）交易；支持 Kalshi 和
Polymarket 两个平台，共用一套接口。

**这是统计 edge 交易，不是无风险套利。** 所有输出都是概率估计，不是保证。模型可能
错，市场可能知道模型不知道的事。把每个信号当成"如果模型校准良好则正期望"，绝不当
成稳赢。

### 核心思想：晚期评论重力

147 部历史片验证：烂番茄分数从解禁早期到结算系统性**下跌**——早期评论偏乐观，公映
前后第二波评论把分数拉低。当评论数足够大、而市场对这个重力定价过高或过低时，买被
错定价的一方就有 edge。贝叶斯模型用 `drift` 参数和系列/导演 `base_rate` 先验来编码
这个规律，蒙特卡洛把两者变成最终分数的完整概率分布。

### 模型状态（已校准，这是实盘正式基线）

参数在留出的**验证组**上**用校准误差选、绝不用收益（PnL）选**——这是本项目最重要的
纪律。当前基线 **`drift=1, prior_strength=20`**（`config.STRATEGY_DEFAULTS`）：

- 验证组校准误差 **0.0083**，2026 样本外 **0.0146**，校准曲线各概率桶都贴着对角线。
- n=80 预测最终分，平均绝对误差 **2.85 分**，84% 的片误差≤5 分，无系统性偏差
  （+0.44）。

关于 `drift`：它每修一个口径 bug 就变一次（4 → 2 → 1）。
**参数"不对劲"往往是别处口径不一致的症状；修口径、重跑校准，参数会自己收敛到真
值。** 现在模型的输入输出都整数化，对齐 RT、Kalshi、Polymarket 三者都用整数
Tomatometer 分数报价和结算的事实。

### 两个平台（以及为什么不能用一个开关）

| | Kalshi | Polymarket |
|---|---|---|
| 找市场 | `kalshi_event` ticker | `polymarket_event_slug` |
| 门槛 | 密集阶梯，`above X` | 稀疏分档（60/70/80/90+） |
| 结算规则 | **严格大于**（`> X`） | **大于等于**（`≥ X`） |
| YES 概率 | `prob_at_least(floor + 1)` | `prob_at_least(floor)` |
| 盘口 | 只有 YES bids（NO 换算） | **两个独立 token**，各有各的盘口 |
| 价格单位 | 整数美分 | 0–1 小数字符串（×100） |
| 结算时刻 | 14:00 UTC | 10:00 AM ET |
| 读数据认证 | 不需要 | 不需要 |

这些差异很深——一个布尔开关会让 `if polymarket:` 散落满代码。所以每个平台相关的规则
都封在**平台适配器**（`src/collectors/platforms/`）里，`monitor` 和报告只跟统一接口
打交道、不知道自己在看哪个平台。核心模型（最终分分布）**平台无关、原样复用**；不同
的只是"怎么用这个分布"（`prob_at_least(floor)` vs `floor+1`）。

### 主命令：实时盯盘

```
py -m scripts.monitor
```

一个配置驱动的循环，每 15 分钟拉一次每部在盯片的实时 RT 分数，跑一次模型，检查每个
激活平台上的每个门槛有没有可交易的 edge。顶部开关：

- `PLATFORM_MODE` —— `"kalshi"` / `"polymarket"` / `"both"`。和每部片在 config 里
  填的字段配合（两层过滤：*开盘平台* ∩ *模式*）决定盯什么。回国不用 Kalshi 后设成
  `"polymarket"`，所有片就只看 Polymarket。
- `COMPACT_MODE` —— `False`（默认）打印每个门槛的概率/价格/edge，有机会的行尾加
  `★`；`True` 只打印带 `★` 的行。

输出给每个机会标上平台和门槛的确切含义（`[kalshi] ≥81` vs `[polymarket] ≥80`）、
模型胜率、edge、以及按目标手数逐档吃单后的真实成交成本。

### 评论采集（RT 数据怎么进来）

RT 的全量评论 API 被 Akamai 挡着，所以有两条路：

1. **`monitor` 实时分数** —— `src/collectors/rt_summary.py` 从电影页的 JSON-LD
   （BeautifulSoup）读当前分数 + 评论数。这是循环自动轮询的。它防御性地解析页面：
   跳过非 `Movie` 的 JSON-LD 块以找到真正的片名（曾经有个 bug 抓到了同名老片），
   页面残缺或畸形时返回 `None` 而不是一个错误的数。

2. **全量评论，手动** —— 把一小段 JavaScript 粘到 RT 页面的 F12 Console。它在真实
   浏览器里跑（带着 cookie 和 Akamai 通行证），自动翻完所有影评人评论（`after` 游标
   就是页码的 base64），下载一个 JSON 文件。把它放进
   `data/new_rt_review_data/raw/` 然后跑：

   ```
   py -m scripts.rt_review_import_report <raw文件.json> <movie_key>
   ```

   它把 RT 原始格式转成项目格式存到 `format/`，并把带日期的质量报告写到 `report/`。

### 质量报告

由 `rt_review_import_report` 打印：

1. **总览** —— 总数、好评/差评、当前新鲜度。
2. **影评人级别** —— 顶级 vs 普通；差距大（顶级更挑剔）是脆弱信号。
3. **打分质量** —— 官方 10 分/字母/5 星/4 星换算：平均、中位、脆弱好评（6.0~7.0，
   最易翻盘）、严重差评。
4. **时间趋势** —— 新鲜度（累计）、平均分（累计）、**每日差评数**（绝对数量，不用小
   样本百分比，所以一条零星差评不再被读成"口碑转向"）。
5. **评论增长预估** —— 每日新增、整体和近 3 日均速、四个 `n_final` 口径（保守/线性近
   3 日/线性整体/衰减），用从今天到结算的剩余天数算。**用来设定每部片的 `n_final`。**
   注意盲点：它外推的是公映前的平缓期，所以公映后结算的片要为第二波评论往上调
   `n_final`。
6. **模型预测** —— 对四个预估 `n_final` 各跑一次模型，让你看到预测分数（也就是这笔
   交易）对评论数猜测有多敏感。

### 加一部电影

复制 `config.py` 里 `WATCHLIST` 的一块，改 key、填值。要手动查、且**必须准**的字段：

- `base_rate` —— 系列/导演历史均分（见项目文档里的 base_rate 填写指南）。
- `rt_movie_id` —— RT 内部 UUID。RT 页面 Ctrl+U → 搜 `emsId`。
- Kalshi 片：`kalshi_event`（ticker——**命名不统一**，去网站确认）和
  `kalshi_settle_date`。
- Polymarket 片：`polymarket_event_slug`（网址里 `/event/` 后面那一串）和
  `polymarket_settle_date`。
- 两个平台都开盘就把两边字段都填。
- `n_final` 可先填默认 200，等评论进来后用增长预估板块细化。
- `embargo_date` 可选（monitor 本来就按 settle date 跟今天比来过滤）。

### 测试

```
py -m pytest -q
```

`tests/test_monitor.py` 单独测纯逻辑——吃单/成本计算、机会门槛判断、两层平台过滤、
Kalshi 与 Polymarket 的规则差异、以及对畸形 RT 页面的防御性解析。（其中一个测试正是
抓出 JSON-LD 同名片 bug 的那个。）

### 诚实的局限

- 模型假设评论**独立同分布**；真实评论会扎堆，所以很可能**低估尾部风险**（口碑崩盘）。
- **还没下过一单真实交易。** 系统能实时盯盘、识别机会；报告里看到的约 28% 是**回测**
  收益（持有到期），不是实盘已实现收益。Kalshi 有硬性的中国合规约束，这正是迁移到
  Polymarket 的原因。
- Polymarket 的 RT 市场目前**流动性薄**（价差大、量小），那里的模型-价格分歧滑点之后
  可能吃不到。
- 实盘的 `n_final` 靠猜；增长预估能收窄猜测但消不掉它，小众片最难定。

---

## Architecture　项目分层

```
rt-kalshi/
├── src/                              # 能力模块（被调用）/ capability modules
│   ├── config.py                     # 全局参数 + 电影清单 + 平台装配 / settings, watchlist, platform wiring
│   ├── model/
│   │   └── bayesian.py               # Beta 后验 + 蒙特卡洛（纯数学，平台无关）
│   ├── strategy/
│   │   └── decide.py                 # Rung / 概率 + 价格 → edge
│   ├── collectors/                   # 采集层（联网）/ data acquisition
│   │   ├── kalshi_client.py          # Kalshi 价格 + 盘口（公开，无需签名）
│   │   ├── rt_summary.py             # 实时分数/n（JSON-LD，防御性解析）
│   │   ├── rt_reviews.py             # 全量评论（被 Akamai 封，保留待复活）
│   │   └── platforms/                # ★ 平台适配层 / platform adapters
│   │       ├── base.py               #   统一接口 Platform
│   │       ├── kalshi.py             #   KalshiPlatform（包装 kalshi_client，floor+1）
│   │       └── polymarket.py         #   PolymarketPlatform（Gamma+CLOB，floor，双 token）
│   └── analysis/
│       └── reviews.py                # 评论质量报告（依赖注入 model_fn，平台无关）
├── scripts/                          # 命令入口 / entry points
│   ├── monitor.py                    # ★ 实时盯盘（PLATFORM_MODE 开关）
│   ├── rt_review_import_report.py    # 手动评论导入 + 报告
│   ├── run_analysis.py               # 单片跑模型看 edge
│   ├── backtest_v2.py                # 校准选参（校准/验证/样本外三向划分）
│   ├── backtest_pnl_realfill.py      # 逐档滑点 PnL 回测（主力）
│   ├── build_samples.py              # 生成校准样本
│   └── check_data_health.py          # 回测前数据体检
├── tests/
│   └── test_monitor.py
├── data/
│   ├── historical/{片}_fullpull.json       # 历史全量评论（校准用）
│   ├── historical_candlesticks/{片}.json   # 官方结算 result（回测判输赢）
│   ├── backtest/samples.csv                # 派生校准表（可重新生成）
│   └── new_rt_review_data/{raw,format,report}/  # 手动评论导入流水线
├── CLAUDE.md                         # 给 Claude Code 的项目纪律
└── README.MD
```

### Layering & discipline　分层与纪律

`src/` holds **capabilities** (called: math, collectors, analysis); `scripts/`
holds **entry points** (thin: parse, call, print). Dependencies flow one way, so
`model/bayesian.py` is pure math reused by live analysis and backtest alike, and
a new venue is a new adapter under `platforms/` without touching the model.

`src/` 装**能力**（被调用的：数学、采集、分析），`scripts/` 装**入口**（薄：解析、
调用、打印）。单向依赖，所以 `model/bayesian.py` 是纯数学、被实时分析和回测共同复用，
加一个新平台只是在 `platforms/` 下加一个适配器、不碰模型。

Two non-negotiable rules, recorded in full in `CLAUDE.md`:
两条不可动摇的纪律，`CLAUDE.md` 里有完整记录：

- **Pick parameters by calibration error, never by PnL.** Keep the 2026 holdout
  genuinely untouched. 用校准误差选参，绝不用 PnL；2026 holdout 保持干净。
- **Trade only at n = 80–150**, where n is well below `n_final` so the signal is
  stable and not over-sensitive to the `n_final` guess. 只在 n=80–150 交易，此时 n
  远小于 n_final，信号稳、对 n_final 猜测不敏感。

---

*Statistical estimate, not a guarantee. Not financial advice.*
*统计估计，不是保证，更不是投资建议。*
