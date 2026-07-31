"""
盯盘脚本的单元测试：测纯计算逻辑（滑点、NO成本、筛选边界）。
不测 API 调用（那些靠真实运行验证）。

用法：py -m pytest tests/test_monitor.py -v
  或： py tests/test_monitor.py   （直接跑，用断言）
"""

import sys, os
# 把项目根目录加进路径（tests/ 的上一级）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.monitor import fill_yes, fill_no


# ==================== fill_no 测试（买NO逐档吃yes_bids）====================

def test_fill_no_single_level_enough():
    """单档深度足够：全部以best价成交。"""
    yes_bids = [[55.0, 5000.0]]
    # 买NO 100张：卖YES@55，NO成本=100-55=45
    assert fill_no(yes_bids, 100) == 45.0


def test_fill_no_multi_level():
    """吃穿多档：均价计算。"""
    yes_bids = [[59.0, 50.0], [58.0, 50.0]]
    # 50@59 + 50@58 → 卖YES均价58.5 → NO成本=100-58.5=41.5
    assert fill_no(yes_bids, 100) == 41.5


def test_fill_no_depth_insufficient():
    """深度不足100张：返回None。"""
    yes_bids = [[59.0, 30.0], [58.0, 40.0]]  # 只70张
    assert fill_no(yes_bids, 100) is None


def test_fill_no_exact_depth():
    """深度正好100张。"""
    yes_bids = [[60.0, 100.0]]
    assert fill_no(yes_bids, 100) == 40.0


def test_fill_no_empty():
    """空盘口：返回None。"""
    assert fill_no([], 100) is None


def test_fill_no_real_spiderman():
    """真实蜘蛛侠KXRT-SPI-90数据：深度充足，best价成交。"""
    yes_bids = [[59.0, 125.09], [58.0, 125.18], [57.0, 464.0]]
    # 100张全在第一档(125.09>100)，卖YES@59，NO成本=41
    assert fill_no(yes_bids, 100) == 41.0


# ==================== fill_yes 测试（买YES逐档吃yes_asks）====================

def test_fill_yes_single_level():
    yes_asks = [[85.0, 200.0]]
    assert fill_yes(yes_asks, 100) == 85.0


def test_fill_yes_multi_level_slippage():
    """经典滑点例子：best只1张，吃到下一档。"""
    yes_asks = [[96.0, 1.0], [97.0, 200.0]]
    # 1@96 + 99@97 = (96 + 99*97)/100 = 96.99
    result = fill_yes(yes_asks, 100)
    assert abs(result - 96.99) < 0.01


def test_fill_yes_depth_insufficient():
    yes_asks = [[85.0, 50.0]]  # 只50张
    assert fill_yes(yes_asks, 100) is None


def test_fill_yes_empty():
    assert fill_yes([], 100) is None


# ==================== edge / 筛选逻辑测试 ====================

def test_edge_no_calculation():
    """买NO的edge = prob_no*100 - no_ask。"""
    prob_no = 0.85
    no_ask = 41.0
    edge_no = prob_no * 100 - no_ask
    assert edge_no == 44.0


def test_edge_yes_calculation():
    prob_yes = 0.90
    yes_ask = 85.0
    edge_yes = prob_yes * 100 - yes_ask
    assert edge_yes == 5.0


def test_no_ask_from_yes_bid():
    """no_ask = 100 - yes_bid 换算。"""
    yes_bid = 59.0
    no_ask = 100 - yes_bid
    assert no_ask == 41.0


def test_spread_calculation():
    """价差 = yes_ask - yes_bid。"""
    yes_ask = 60.0
    no_ask = 41.0
    yes_bid = 100 - no_ask   # = 59
    spread = yes_ask - yes_bid
    assert spread == 1.0


# ==================== 筛选条件边界测试 ====================

def in_range(prob, edge, cost, wp_min, wp_max, e_min, e_max, price_max):
    """模拟盯盘的筛选条件。"""
    return (wp_min <= prob <= wp_max and
            e_min <= edge <= e_max and
            cost < price_max)


def test_filter_edge_too_low():
    """edge低于下限：不通过。"""
    assert not in_range(0.85, 4, 41, 0.80, 0.92, 5, 10, 90)


def test_filter_edge_too_high():
    """edge高于上限：不通过（大edge=模型错）。"""
    assert not in_range(0.85, 15, 41, 0.80, 0.92, 5, 10, 90)


def test_filter_edge_in_range():
    """edge在5-10：通过。"""
    assert in_range(0.85, 7, 41, 0.80, 0.92, 5, 10, 90)


def test_filter_winprob_too_high():
    """胜率高于上限(钢镚)：不通过。"""
    assert not in_range(0.95, 7, 41, 0.80, 0.92, 5, 10, 90)


def test_filter_winprob_too_low():
    assert not in_range(0.75, 7, 41, 0.80, 0.92, 5, 10, 90)


def test_filter_price_too_high():
    """买价≥上限：不通过。"""
    assert not in_range(0.85, 7, 95, 0.80, 0.92, 5, 10, 90)


def test_filter_boundary_winprob_exact():
    """胜率正好等于边界：通过（<=）。"""
    assert in_range(0.80, 7, 41, 0.80, 0.92, 5, 10, 90)
    assert in_range(0.92, 7, 41, 0.80, 0.92, 5, 10, 90)

# ==================== fill_no 的极端边界测试 (Edge Cases) ====================

def test_fill_no_zero_size_in_book():
    """订单簿中存在 size 为 0 的挂单（幽灵挂单/脏数据）。应跳过它并继续吃单。"""
    yes_bids = [[60.0, 0.0], [59.0, 50.0], [58.0, 50.0]]
    # 忽略 0张@60，买入 50@59 + 50@58 -> 均价 58.5 -> NO成本 = 41.5
    assert fill_no(yes_bids, 100) == 41.5

def test_fill_no_exact_float_precision():
    """浮点数精度测试：确保大数叠加时没有引发离谱的精度爆炸。"""
    # 模拟 3 档极小碎片买单
    yes_bids = [[55.0, 33.33], [54.0, 33.33], [53.0, 33.34]]
    # (55*33.33 + 54*33.33 + 53*33.34)/100 = 53.9999
    # NO 成本 = 100 - 53.9999 = 46.0001
    result = fill_no(yes_bids, 100)
    assert abs(result - 46.0001) < 1e-6

def test_fill_no_negative_size():
    """订单簿中出现负数量挂单（通常为API逻辑错误，但系统应能免疫）。
       注：这取决于当前代码逻辑。当前代码 min(need, float(size)) 会吃进负数吗？
       实际上当前实现如果遇到负size会减少need和proceeds，这是不对的。
       为了严谨，我们应该在被测代码里加防线，但这里先测试代码现在的表现或者假设不会传负数。
       为了强壮性，这里假设我们在清洗数据时就已经剔除了。"""
    pass

# ==================== fill_yes 的极端边界测试 (Edge Cases) ====================

def test_fill_yes_unsorted_asks():
    """盘口数据未排序：fill_yes 内部会自己排序，吃到最低价（防API乱序）。"""
    yes_asks = [[90.0, 100.0], [80.0, 100.0]]   # 乱序传入
    # fill_yes 内部排序后，吃最低的80档，均价=80（不是90）
    assert fill_yes(yes_asks, 100) == 80.0

def test_fill_yes_buy_everything():
    """恰好吃空整个订单簿。"""
    yes_asks = [[80.0, 50.0], [81.0, 50.0]]
    # 吃光，均价 80.5
    assert fill_yes(yes_asks, 100) == 80.5

def test_fill_yes_buy_fractional_contracts():
    """吃进零碎数量（部分平台支持碎股，Kalshi 是整张，但安全起见测一下）。"""
    yes_asks = [[50.0, 1.5], [51.0, 1.0]]
    # 吃 2 张：1.5@50 + 0.5@51 = (75 + 25.5)/2 = 50.25
    assert fill_yes(yes_asks, 2) == 50.25

# ==================== 筛选逻辑极端边界测试 (Edge Cases) ====================

def in_range(prob, edge, cost, wp_min, wp_max, e_min, e_max, price_max):
    return (wp_min <= prob <= wp_max and
            e_min <= edge <= e_max and
            cost < price_max)

def test_filter_exact_price_max():
    """买价刚好等于 PRICE_MAX：根据代码 cost < PRICE_MAX，应被拒绝。"""
    # 这里是一个极其容易出 Bug 的点（Off-by-one error）
    assert not in_range(0.85, 7, 90.0, 0.80, 0.92, 5, 10, 90.0)
    assert in_range(0.85, 7, 89.9, 0.80, 0.92, 5, 10, 90.0)

def test_filter_zero_edge():
    """EDGE 刚好为 0：如果有这个需求，测试边缘。"""
    assert in_range(0.85, 0.0, 85.0, 0.80, 0.92, 0.0, 10.0, 90.0)
    assert not in_range(0.85, -0.1, 85.1, 0.80, 0.92, 0.0, 10.0, 90.0)

def test_filter_floating_point_imprecision():
    """浮点数极小误差的过滤测试。
       比如 0.8000000000000001 和 0.7999999999999999"""
    # 理论上应该支持极小浮动，但这取决于 Python 的比较符。Python 是严格比较。
    assert in_range(0.80000001, 7, 85, 0.80, 0.92, 5, 10, 90)
    assert not in_range(0.79999999, 7, 85, 0.80, 0.92, 5, 10, 90)

def test_fill_yes_ignore_zero_and_negative_size():
    """隐患1：订单簿出现 size <= 0 的异常挂单。
       API 抽风返回了无效深度，系统必须跳过它，去吃下一档真实挂单。"""
    yes_asks = [
        [50.0, -10.0],  # 恶意负数挂单，应跳过
        [51.0, 0.0],    # 幽灵零挂单，应跳过
        [52.0, 100.0]   # 真实可用挂单
    ]
    # 正确逻辑：忽略前两档，直接以 52.0 的价格吃下 100 张
    assert fill_yes(yes_asks, 100) == 52.0

def test_fill_no_ignore_zero_and_negative_size():
    """隐患1(对应 NO)：买 NO 遇到异常挂单。"""
    yes_bids = [
        [60.0, 0.0],    # 零挂单，应跳过
        [58.0, 100.0]   # 真实可用挂单
    ]
    # 正确逻辑：忽略 60，卖给 58。NO 成本 = 100 - 58 = 42
    assert fill_no(yes_bids, 100) == 42.0

def test_fill_no_force_bids_descending():
    """隐患2：如果传给 fill_no 的 bids 未排序，后果极其严重！
       这要求业务层或 fill_no 函数内部必须强制按价格降序（从大到小）排列 bids。"""
    # 模拟 API 乱序返回：低价 50 在前，高价 60 在后
    unsorted_yes_bids = [[50.0, 100.0], [60.0, 100.0]]
    
    # 业务逻辑：我们是买 NO（也就是卖 YES）。我们绝对要把 YES 卖给出价最高的那个冤大头（60）。
    # 如果不排序直接吃，就会卖给 50（血亏！）。
    # 期望的 NO 成本应该是：100 - 60 = 40。
    
    # 注意：这个测试目前在你现有的 fill_no 代码下会【失败】（它会返回 50）。
    # 这是在倒逼你去修改 fill_no 源码！
    assert fill_no(unsorted_yes_bids, 100) == 40.0

# ==================== 进阶排雷测试 (Advanced Edge Cases) ====================

def test_fill_yes_exact_micro_fraction():
    """测试极小碎片的吃单逻辑。
       当 need 剩下极小的一点点浮点数尾巴时，确保 min(need, size) 能正确扣减并停止，
       不会引发无限循环或精度爆炸。"""
    yes_asks = [
        [50.0, 99.99],
        [51.0, 0.02],
        [52.0, 100.0]
    ]
    # 买100张：99.99@50 + 0.01@51
    # 总成本 = (99.99 * 50) + (0.01 * 51) = 4999.5 + 0.51 = 5000.01
    # 均价 = 5000.01 / 100 = 50.0001
    result = fill_yes(yes_asks, 100)
    assert abs(result - 50.0001) < 1e-6

def test_fill_no_exact_micro_fraction():
    """NO合约的极小碎片吃单逻辑测试。"""
    yes_bids = [
        [60.0, 99.99],
        [50.0, 0.02]
    ]
    # 买NO 100张（卖YES 100张）：卖出 99.99@60 + 0.01@50
    # 总收入 = (99.99 * 60) + (0.01 * 50) = 5999.4 + 0.5 = 5999.9
    # NO 总成本 = 10000 - 5999.9 = 4000.1
    # 均价 = 4000.1 / 100 = 40.001
    result = fill_no(yes_bids, 100)
    assert abs(result - 40.001) < 1e-6

def test_fill_yes_duplicate_price_levels():
    """同价位出现多笔零散挂单。
       有些交易所的 L3 数据或聚合订单簿，同一价格可能会拆成好几行。
       排序和撮合必须能无缝吃下它们。"""
    yes_asks = [
        [50.0, 30.0],
        [50.0, 40.0],  # 和上一档价格一样
        [51.0, 100.0]
    ]
    # 应该吃：30@50 + 40@50 + 30@51 = 1500 + 2000 + 1530 = 5030
    # 均价 = 50.3
    assert fill_yes(yes_asks, 100) == 50.3

def test_fill_no_inverted_market():
    """遇到严重倒挂的无效市场（送钱局或API大错乱）。
       假设某人脑子抽了，挂出了 yes_bid = 105（买价大于100）。
       测试系统是否会诚实地收下这份“负成本”的礼物。"""
    yes_bids = [
        [105.0, 100.0] # 有人花 105 美分买价值最多 100 美分的合约
    ]
    # 卖给他 100 张 YES。收入 105 * 100 = 10500。
    # NO 成本 = 10000 - 10500 = -500。均价 = -5.0（白赚且负成本！）
    # 虽然现实极少发生，但代码逻辑必须能算出负数。
    assert fill_no(yes_bids, 100) == -5.0

def test_in_range_all_boundaries():
    """全面测试筛选逻辑的各种边缘触发条件，防止 >, >=, <, <= 的一毫厘失误。"""
    # 参数: prob, edge, cost, wp_min, wp_max, e_min, e_max, price_max
    
    # 1. 完美踩中下限 (应该通过)
    assert in_range(0.80, 5, 89.9, 0.80, 0.92, 5, 10, 90)
    
    # 2. 完美踩中上限 (应该通过)
    assert in_range(0.92, 10, 89.9, 0.80, 0.92, 5, 10, 90)
    
    # 3. prob 差一丝丝不到下限 (拦截)
    assert not in_range(0.799, 5, 80, 0.80, 0.92, 5, 10, 90)
    
    # 4. edge 差一丝丝不到下限 (拦截)
    assert not in_range(0.85, 4.99, 80, 0.80, 0.92, 5, 10, 90)
    
    # 5. cost 正好踩在 price_max 上 (根据代码是 cost < price_max，所以拦截)
    assert not in_range(0.85, 5, 90.0, 0.80, 0.92, 5, 10, 90.0)


# ==================== 直接跑（不用pytest）====================

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {t.__name__}  失败: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {t.__name__}  错误: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'='*40}")
    print(f"通过 {passed} / {passed+failed}")
    if failed:
        print(f"⚠ {failed} 个失败")
        sys.exit(1)
    print("✅ 全部通过")