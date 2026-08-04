# CLAUDE.md — rt-kalshi-edge 项目说明

> 这份文档给 Claude Code（和任何接手的人）快速理解本项目。
> 项目所有者：DIDI。开发环境：Windows，VS Code，`.venv`，从项目根目录用 `py -m` 运行。
> 交流语言：中英双语（DIDI 主要用中文）。

---

## 0. 一句话概述

用**烂番茄（Rotten Tomatoes, RT）早期影评数据**预测 **Kalshi 二元合约**的结算结果，
寻找市场定价与模型概率之间的正期望（edge）交易机会。核心是一个贝叶斯模型 +
严格的回测/校准纪律 + 一个半自动实盘盯盘系统。

**这是统计 edge 交易，不是套利。** 每个输出是概率估计，不是保证。

---

## 1. 核心策略：晚期重力（Late-Review Gravity）

**核心假设**：RT 的 Tomatometer 分数会从早期影评到最终结算**系统性下跌**
（早期影评偏乐观，晚期影评把分数拉低）。147 部片验证：平均下跌约 2.44 分，
约 63% 的片下跌，且 n（影评数）越大跌幅越小（单调收敛）。

**交易逻辑**：当 n≥80、市场对某门槛的定价没有充分反映这个系统性下跌时，
买入被错误定价的一方（历史上主要是买 NO，顺应"分数会跌"）。

**结算规则**：Kalshi "above X" 合约是**严格大于**——最终分必须 **> X**（即 ≥ X+1）
YES 才赢。所以模型判断 YES 概率用 `prob_at_least(floor + 1)`。
- YES above 20 = 最终分 ≥ 21 才赢。
- NO above 20 = 最终分 ≤ 20 才赢（**包含 20**，不是 ≤19）。

---

## 2. 模型（src/model/bayesian.py）

贝叶斯 + 蒙特卡洛模型，预测结算时刻的最终分数分布。

**输入 `ModelInputs`：**
- `score_now`：当前 RT 分数 %（**已整数化，对齐 RT 官方整数口径**）
- `n_now`：当前影评数（最关键的输入）
- `base_rate`：系列/导演历史均分（先验中心），**手工核实填入 config**
- `prior_strength`：先验信任度（"伪评论数"）
- `n_final`：预计结算时的总影评数
- `drift`：早期乐观偏差修正（要减掉的点数）

**内部逻辑：**
1. 用 `score_now × n_now` 反推当前好评数 k。
2. base_rate + prior_strength 构造 Beta 先验。
3. 观测 k 更新后验，得到"真实好评率"的分布。
4. 减去 drift（早期乐观修正）。
5. 对 `n_final - n_now` 条未来评论做二项模拟。
6. `final_scores = round((k + new_fresh) / n_final × 100)` —— **四舍五入到整数，对齐 RT 结算口径**。

**输出 `ModelResult`：**
- `mean`：模拟最终分均值（= 预测最终分）
- `sd`：标准差
- `final_scores`：几十万个模拟最终分的数组
- `prob_at_least(threshold)`：P(最终分 ≥ threshold)，= 买 YES 胜率
- `prob_below(threshold)`：P(最终分 < threshold)，= 买 NO 胜率

**⚠ 口径一致性（极重要）**：模型输入（score_now）和输出（final_scores）
**都必须整数化**，因为 RT 官方分数从头到尾是四舍五入整数，Kalshi 用 RT 整数结算。
实盘 rt_summary 抓的也是整数。所有算 score 的地方（build_samples.py、
build_samples_pnl.py、backtest_pnl_realfill 的 score_n_at）都要 `round(fresh/n*100)`（整数）。

---

## 3. 当前最优参数（务必用这套）

```
drift = 1
prior_strength = 20
n_final = 200（实盘固定估计值；见下方 n_final 说明）
```

**这套参数是怎么来的（选参纪律，铁律）：**
- **参数只用验证组校准误差（CE）选，绝不用 PnL 选。** 用 PnL 选会过拟合
  （PnL 是十几笔的噪声）。
- 三向数据划分：**校准集 / 验证集 / 2026 holdout**。
- 校准组最优往往偏好大 drift（过拟合），**不直接用**；用**验证组最优**。
- 最终用 **2026 holdout** 确认泛化（holdout 全程不能碰，不能用它调任何参数）。

**参数演变史（每次都是修了一个口径 bug，drift 更接近真值）：**
| 阶段 | 口径状态 | 验证组最优 drift |
|---|---|---|
| 早期 | 严格大于 bug + 连续分数 | 4（在补偿 bug） |
| 修严格大于（floor+1） | 连续分数 | 0 |
| 修四舍五入（模型输出对齐整数） | 输出整数，输入连续 | 2 |
| **整数化输入（当前）** | 输入输出全整数，对齐 RT | **1（当前，最干净）** |

drift=1 的最新验证：验证组 CE=0.0083，2026 样本外 CE=0.0146，校准曲线高度吻合。

**教训**：当 drift 看起来"需要非零值"时，先怀疑有没有隐藏的口径 bug 在 compensate。
`drift=4` 曾是严格大于 bug 的 artifact，`drift=0/2` 曾是四舍五入口径的 artifact。

**n_final 说明**：实盘无法预知最终评论数（未来的数），只能估。经验证：
分片估计误差太大，故**统一用 200**。但只在 **n 远小于 n_final（如 n=80-150）时交易**——
那时还有大量不确定性，概率不极端，信号稳、对 n_final 误差不敏感。
n 接近或超过 n_final 时（如蜘蛛侠 n=311），模型概率会极端收敛（0/1），信号对 n_final
极度敏感、不可靠，**不该交易这种片**。

---

## 4. 目录与脚本分层

> 注：部分文件在项目里位于 `src/`（如 `src/model/bayesian.py`、
> `src/collectors/rt_summary.py`、`src/config.py`），部分薄入口在 `scripts/`。
> 下面按功能分组。从项目根用 `py -m` 运行。

### 4.1 模型与决策层
- **bayesian.py**（`src/model/`）：核心贝叶斯+蒙特卡洛模型。`run_model(ModelInputs)` → `ModelResult`。
- **decide.py**：决策层。拿模型的终值分布 + Kalshi 各档价格，算每个门槛的
  YES/NO edge，挑出"最稳健"和"最佳价值"推荐。含 `Rung` 数据类（一个门槛：
  `t`=门槛, `yes_price`, `no_price`, `ticker`=真实 market ticker）。
- **config.py**（`src/`）：`WATCHLIST` 电影清单（见数据结构章节）。

### 4.2 数据抓取（collectors）
- **rt_summary.py**（`src/collectors/`）：★实盘用★。抓 RT 主页面 JSON-LD，
  得到当前 score(整数) + n。**优先用 rt_movie_id(UUID)** 构造 URL（RT 自动重定向到
  正确片，避免同名老片污染）。UUID 抓到正确页面就用，即使没影评（未上映）也不降级
  到 slug——**这个"不降级"很关键**，否则未上映片会撞同名老片抓到错误数据。
  提供 `fetch_summary`（抛异常版）和 `fetch_summary_safe`（返回 None 版，盯盘循环用）。
- **rt_reviews.py**（`src/collectors/`）：抓全量评论明细（用于历史回测数据集）。
  **已被 RT 的 Akamai Bot Manager 封（401）**，因为它调的 napi/rtcf 评论 API 需要
  动态质询 token。**保留不删**（历史 150 部数据已抓完，不受影响；将来可用 Playwright 复活）。
- **fetch_reviews.py**（`scripts/`）：薄入口，抓当前开盘片的评论 + orderbook 并存档、体检、打印分析命令。
- **fetch_historical.py**（`scripts/`）：薄入口，抓【已结算历史片】评论 → `data/historical/`，供回测。
- **fetch_candlesticks.py**（`scripts/`）：抓已结算历史片的全门槛历史 K 线 + 结算元数据
  （含 final_score、settle_date、**各门槛 result（Kalshi 官方 yes/no 结算，标准答案）**）。
- **fetch_all_historical.py**（`scripts/`）：批量入口，一键抓所有已结算片的评论+K线。
- **fetch_orderbooks.py**（`scripts/`）：从 **Predexon** 拉 Kalshi sub-cent orderbook 历史快照
  （Predexon 存历史，Kalshi 官方 API 不存历史）。数据从 2026-01-08 开始。
  每门槛每小时保留一个代表快照（HH:59:59 最近的）。

### 4.3 Kalshi 实时 API
- **kalshi_client.py**：★实盘用★。
  - `get_ladder_live(event_ticker)`：查某 event 下所有门槛 market，返回 `Rung` 列表
    （门槛 + best 价）。**裸请求**（markets 端点公开，暂时不需签名）。
  - `fetch_market_orderbook(ticker)`：★带 RSA-PSS 签名★，拿单门槛的逐档深度。
    返回 `{yes_bids:[[price_cent,size]降序], no_bids, ticker}`。价格美元字符串×100转美分。
  - 签名基础设施：`_load_env`、`_get_private_key`（缓存）、`_sign`、`_get_signed`。
    认证 header：KALSHI-ACCESS-KEY（key id）、KALSHI-ACCESS-SIGNATURE（RSA-PSS 签名，
    message=timestamp+method+path）、KALSHI-ACCESS-TIMESTAMP（毫秒）。
    BASE_URL = `https://external-api.kalshi.com`。API key ID 存 .env（KALSHI_API_KEY），
    私钥文件 `rt-kalshi-monitor-private-key.txt`（gitignore）。**只读权限的 key**（盯盘只读，安全）。

### 4.4 样本构建（回测前处理）
- **build_samples.py**：从评论+K线生成 `data/backtest/samples.csv`，供 **backtest_v2 校准**。
  第 76 行算 score（**整数化**：`round(fresh/len*100)`）。字段见数据结构章节。
- **build_samples_pnl.py**：生成 PnL 样本（给旧的 backtest_pnl_hourly 等用）。
  第 153 行算 score（也应整数化）。

### 4.5 回测与校准
- **backtest_v2.py**：★选参数用★。读 samples.csv，扫描 drift×prior 网格，
  用**验证组校准误差**选最优，再用 2026 holdout 确认。**这是选 drift/prior 的权威脚本。**
  校准指标：CE（校准误差）、Brier。输出校准曲线（预测概率 vs 实际频率）。
- **backtest.py / backtest_pnl.py / backtest_pnl_hourly.py**：早期回测脚本（读 score_at_decision）。
- **backtest_pnl_realfill.py**：★当前主力 PnL★。真实逐档滑点回测。
  - 市场价全用 orderbook（best bid/ask 算 edge，逐档算真实成交）。
  - n/score/n_final 从评论算（score 整数化：第 87 行 score_n_at）。
  - `fill_yes`/`fill_no`：逐档吃单算真实成交均价。深度不足 100 张则跳过。
  - 输赢用 orderbook 数据里的 `result` 字段（Kalshi 官方结算，标准答案）。
  - 一片一注、持有到期、固定 100 张。含 SPREAD_MAX、n_final 三档开关
    （USE_N_FINAL_EST > USE_FIXED_N_FINAL > 真实值）。
- **backtest_pnl_multistrike.py**：多门槛 + 仓位管理版。同 floor 只买一次、同片多 floor
  可各买；三约束仓位 `min(本金RISK_PCT%, 深度滑点≤MAX_SLIPPAGE_CENT, 上限MAX_CONTRACTS)`；
  单片总仓位上限 MAX_MOVIE_EXPOSURE_PCT；资金滚动、先到先得、最大回撤、按月统计、单片集中度。
  **结论：多门槛是方差放大器不是 edge 放大器**（放大收益也放大回撤，让 2/3 月变差）。
- **diagnose_big_edge.py**：诊断异常大 edge 的交易。

### 4.6 实盘盯盘
- **monitor.py**（`scripts/`）：★半自动实盘盯盘★。每 15 分钟循环。
  - `get_watching_movies()`：从 WATCHLIST **逻辑筛**当前该盯的片
    （`should_watch(settle, embargo, today)`：还没结算 且 已解禁）。新片加进 config 自动盯，
    结算后自动退出。**不单独维护盯盘列表。**
  - `check_movie`：rt_summary 拿 score/n → `is_valid_rt_data` 校验（None/负/超范围/非数字则跳过）
    → n<80 跳过 → get_ladder_live 拿门槛初筛 → `evaluate_rung` 判断机会
    → 符合的 fetch_market_orderbook 拿深度算真实成本 → 打印机会。
  - `evaluate_rung(prob_yes, yes_ask, no_ask)`：纯函数，判断单门槛是否机会
    （方向/胜率区间/edge区间/买价/价差）。返回 (方向, edge, 胜率, 买价) 或 None。
  - `fill_yes`/`fill_no`：逐档吃单。**自我防护**：过滤 size≤0 的垃圾挂单、
    函数内部强制排序（不依赖输入已排序）。
  - 去重：`notified` 是 dict `{(movie,floor): 上次edge}`。首次必提醒，之后
    edge ≥ 上次 + EDGE_IMPROVE_THRESHOLD 才再提醒（edge 变好再提醒），变差不提醒。
  - 顶部策略参数可随时改。第一版打印到终端（下一步接 Discord/Telegram）。
- **run_analysis.py**：命令行给一部片跑模型，打印 YES/NO edge 表和推荐。
- **show_report.py**：读已存的评论 JSON，重新出质量报告（纯本地，不联网）。

### 4.7 工具与测试
- **reviews.py**：评论解析、质量报告、趋势构建。含 `_is_fresh`、`_parse_date`（返回 .date()）。
- **check_data_health.py**：回测前数据体检，揪脏数据。
- **test_model.py**：模型单元测试。
- **test_monitor.py**（`tests/`）：★盯盘逻辑测试★。测纯计算（fill_yes/fill_no 各种深度/
  零负size/乱序、is_valid_rt_data 各种异常、evaluate_rung 机会判断边界、should_watch config
  各种情况、10个刁钻边界）。从项目根跑 `py -m pytest tests/test_monitor.py -v`。

---

## 5. 数据结构

### 5.1 config.py 的 WATCHLIST（每部电影一个条目）
```python
"spider_man_brand_new_day": {
    "embargo_date": "2026-07-28",      # 手工 Google 搜索填（解禁日）。查不到就不写这字段
    "title": "Spider-Man: Brand New Day",
    "base_rate": 88,                    # 手工核实的先验均分（关键，模型用）
    "n_final": 200,                     # 占位符，代码不读它（realfill 动态算或用固定200）
    "kalshi_event": "KXRT-SPI",         # Kalshi event ticker，拿门槛用
    "kalshi_settle_date": "2026-08-03", # 结算日，筛选盯盘范围用
    "rt_movie_id": "0603023c-...",      # ★RT 电影 UUID★，抓 RT 用（最可靠，避免同名歧义）
    # "final_score_official": 91,       # 官方最终分。盯盘时留空（未结算），结算后填，回测用
    # "rt_slug": "...",                 # 可选，rt_summary 的 slug 后备（一般用 UUID 就够）
    # "lift_date": "...",               # 按最早评论算的解禁日（优先用 embargo_date）
}
```
**盯盘新片必填**：base_rate、kalshi_event、rt_movie_id、kalshi_settle_date。
**可留空**：final_score_official（未结算）、embargo_date（查不到就不写这字段，
别写字符串 "None"）、n_final（用固定 200）。

### 5.2 samples.csv（build_samples 生成，v2 校准读）
每行一个 (电影, 决策时点, 门槛) 样本：
`movie_key, decision_day, decision_date, score_at_decision(整数), n_at_decision,
base_rate, floor, yes_ask, yes_bid, spread, volume, final_score, result(yes/no), settle_date`

### 5.3 orderbooks_merged.json（merge 生成，realfill 读）
```
{ movie_key: {
    settle_date, final_score, event_ticker,
    markets: { ticker: {
        floor, result(yes/no 官方结算),
        hourly_snapshots: { "YYYY-MM-DD HH:00": {
            ts(毫秒), best_bid, best_ask, yes_bids:[[price,size]], yes_asks, ...
        }}
    }}
}}
```
切窗口 [解禁日美西12点, 结算14:00 UTC]，深度档位完整保留。约 109MB，39 部 2026 片。

---

## 6. data/ 目录结构

- **data/historical/{movie_key}_fullpull.json**：已结算片的全量评论明细（逐条，
  含 sentiment、date 等）。回测算 score/n/n_final 的原料。~150 部。
- **data/historical_candlesticks/{movie_key}.json**：已结算片的历史 K 线 + 结算元数据
  （含 final_score、settle_date、各门槛 result、market ticker）。
- **data/orderbooks/{movie_key}.json**：Predexon 拉的 sub-cent orderbook 历史快照
  （每门槛每小时一个代表快照）。40 个文件（含 1 个空的 minions）。
- **data/backtest/orderbooks_merged.json**：合并+切窗口后的大文件（realfill 用）。
- **data/backtest/samples.csv**：v2 校准样本。
- **data/backtest/results/**：回测结果输出（pnl 报告、CSV、v2 校准 json）。
- **data/snapshots/{movie}/**：当前开盘片的带日期评论快照。

---

## 7. 数据源与平台

- **Rotten Tomatoes**：分数来源。实时 score/n 靠抓主页面 JSON-LD（rt_summary，用 UUID）。
  全量评论 API 被 Akamai 封（rt_reviews 401）。
- **Kalshi**：预测市场（受美国 CFTC 监管）。实时盘口用官方 API（RSA-PSS 签名）。
  **不存历史 orderbook**。
- **Predexon**（`https://api.predexon.com/v2/kalshi/orderbooks-subcent`）：sub-cent
  历史 orderbook，免费，x-api-key 头。历史从 2026-01-08 开始。key 存 .env（PREDEXON_API_KEY）。
- **.env**：PREDEXON_API_KEY、KALSHI_API_KEY。
- **rt-kalshi-monitor-private-key.txt**：Kalshi RSA 私钥（gitignore，只读权限 key）。

---

## 8. 项目当前状态（已完成 / 进行中）

**已完成：**
- 贝叶斯模型 + 蒙特卡洛，口径全整数化对齐 RT。
- 三向数据划分 + 验证组校准误差选参纪律。当前参数 drift=1/prior=20（验证组选+2026确认）。
- 重力假设验证（147 部，系统性下跌）。
- 真实逐档滑点 PnL（backtest_pnl_realfill）。
- 多门槛+仓位管理 PnL（结论：方差放大器，谨慎用）。
- RT 实时数据（rt_summary，UUID，解决同名老片污染 bug）。
- Kalshi 实时 API（签名认证测通，orderbook 拿到逐档深度）。
- 半自动盯盘 monitor.py（筛片/RT/门槛/机会识别/去重/edge变好再提醒）+ 单元测试。
- 各种防护：输入合理性校验、滑点防抽风（零负size/乱序）、未解禁/n<80/抓取失败不崩。

**进行中 / 下一步：**
- 接 Discord/Telegram 通知（盯盘 print → 发消息）。
- 服务器部署（**先解决合规**：回中国后 Kalshi 访问合规问题；考虑 Polymarket 国际版，
  但 Polymarket 结算规则不同——如 above 用 ≥ 而非严格 >——需重新评估整套逻辑）。
- 趁在美国做小仓位手动实盘验证（用盯盘脚本发现机会，手动下单）。

**已知问题 / 风险：**
- **"你算的 fresh 比例" vs "RT 官方 Tomatometer"可能有口径偏差**——边界门槛
  （如 mercy above 20）可能因此判错。整数化缓解了一部分，但根本偏差待验证。
- config 里 final_score_official 曾有填错（minions 填 51 实际 91；joker 待查）——
  会污染验证结果，填之前核对。
- 从中国访问 Kalshi 的合规是硬门槛，未解决。
- 实盘从未真实下过单（所有成交都是回测模拟）。

---

## 9. 关键纪律（Claude Code 请遵守）

1. **参数只用验证组校准误差选，绝不用 PnL 选。** PnL 好看≠参数对（会过拟合）。
2. **保持 holdout（2026）干净**：不用它调任何参数/认知；只用于最终确认泛化。
3. **口径一致**：score 输入、final_scores 输出、结算，全部整数（对齐 RT）。
   校准（v2）和 PnL（realfill）和盯盘（monitor）必须同口径、同参数。
4. **当某参数（如 drift）"看起来需要非零/特殊值"时，先怀疑隐藏的口径 bug 在补偿它。**
5. **只在 n=80-150 交易**（远小于 n_final，信号稳）；避开 n 已很大的片（概率极端、信号敏感）。
6. **多门槛/Kelly/复利是放大器不是发动机**：先证明固定下注的稳定 edge，再放大。
7. **不信任外部数据**：RT/Kalshi API 可能抽风（None/负数/超范围/乱序/空盘口）——
   所有外部输入先校验合理性再用。用错电影数据 = 下错单。
8. **改动数据结构/口径后，必须重跑校准 + 回归测试**（参数可能跟着变，别沿用旧值）。
9. **DIDI 有 pushback 文化**：会质疑不符合设计意图的建议，且常常是对的。有分歧时讲清依据。

---

## 10. 常用命令

```bash
# 抓当前开盘片（评论+盘口）
py -m scripts.fetch_reviews --movie toy_story_5
# 抓已结算历史片（回测用）
py -m scripts.fetch_historical --movie some_movie
# 给一部片跑模型看 edge
py -m run_analysis --movie toy_story_5
# 选参数（校准）
py backtest_v2.py
# 真实滑点 PnL
py -m scripts.backtest_pnl_realfill    # 注意实际文件名无 .py
# 盯盘（半自动实盘）
py -m scripts.monitor
# 测试
py -m pytest tests/test_monitor.py -v
# 实时抓某片当前 score/n
py -m src.collectors.rt_summary toy_story_5
```