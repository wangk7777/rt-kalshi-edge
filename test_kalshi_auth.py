"""测试整合后的 kalshi_client：门槛列表 + 逐档orderbook。"""
from src.collectors import kalshi_client as kc

EVENT = "KXRT-SPI"          # 蜘蛛侠（正在交易）
TEST_TICKER = "KXRT-SPI-90" # 一个门槛

print("=" * 50)
print("测试1: get_ladder_live（门槛列表，裸请求）")
print("=" * 50)
try:
    rungs = kc.get_ladder_live(EVENT)
    for r in rungs:
        print(f"  门槛{r.t:.0f}: yes_ask={r.yes_price:.0f}¢ no_ask={r.no_price:.0f}¢")
except Exception as e:
    print(f"  ✗ 失败: {e}")

print("\n" + "=" * 50)
print("测试2: fetch_market_orderbook（逐档深度，带签名）")
print("=" * 50)
try:
    ob = kc.fetch_market_orderbook(TEST_TICKER)
    print(f"  ticker: {ob['ticker']}")
    print(f"  yes_bids 前5档(降序): {ob['yes_bids'][:5]}")
    print(f"  no_bids 前5档(降序): {ob['no_bids'][:5]}")
    # 演示：买NO 100张的成本（吃yes_bids）
    if ob["yes_bids"]:
        best_yes_bid = ob["yes_bids"][0][0]
        print(f"  best yes_bid={best_yes_bid:.0f}¢ → 买NO成本≈{100-best_yes_bid:.0f}¢")
    else:
        print(f"  ⚠ yes_bids为空（没人买YES，这个门槛没法按盘口买NO）")
except Exception as e:
    print(f"  ✗ 失败: {e}")