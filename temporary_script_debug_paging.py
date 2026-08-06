"""
验证：小众历史片（最终 n<100）在 n=N_AT 时，模型预测最终分 vs 真实最终分。
回答：小众片能不能在早期（n=N_AT）就交易（分数是否已稳定、可预测）。
排除 config 里 exclude_from_backtest=True 的片。

USE_FIXED_NFINAL 开关：
  True  → 用 FIXED_NFINAL_GUESS（模拟实盘：你不知道真实n，统一猜一个值）
  False → 用真实 total_n（上帝视角：假设完美预知最终评论数，看模型上限）

用法：py temporary_script_debug_paging.py
"""

"""验证平台适配器：两个平台都能 get_rungs + yes_prob。"""
from src import config
from src.model.bayesian import ModelInputs, run_model
from src.collectors.platforms.kalshi import KalshiPlatform
from src.collectors.platforms.polymarket import PolymarketPlatform

# 跑个模型结果备用
res = run_model(ModelInputs(score_now=85, n_now=120, base_rate=80,
                            prior_strength=20, n_final=200, drift=1), n_sims=50000)

# 测 Kalshi 适配器（用一个有 kalshi_event 的片）
kp = KalshiPlatform()
print("Kalshi yes_prob(floor=80):", kp.yes_prob(res, 80), "(用floor+1=81)")

# 测 Polymarket 适配器
pp = PolymarketPlatform()
print("Polymarket yes_prob(floor=80):", pp.yes_prob(res, 80), "(用floor=80)")

# 验证规则差异：同样floor，两平台概率不同
print("\n规则差异验证：")
print(f"  Kalshi P(≥81) = {kp.yes_prob(res, 80):.3f}")
print(f"  Polymarket P(≥80) = {pp.yes_prob(res, 80):.3f}")
print("  (Polymarket应该略高，因为≥80比≥81宽松)")

# 测 Polymarket get_rungs（用PAW Patrol的slug）
paw_cfg = {"polymarket_event_slug": "paw-patrol-the-dino-movie-rotten-tomatoes-score-20260709174855589"}
rungs = pp.get_rungs(paw_cfg)
print(f"\nPolymarket get_rungs: 拿到 {len(rungs)} 档")
for r in rungs:
    print(f"  门槛{r.t}: YES {r.yes_price}¢ NO {r.no_price}¢")