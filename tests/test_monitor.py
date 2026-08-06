"""
盯盘脚本单元测试：覆盖纯计算逻辑 + 平台适配 + edge cases。
不测真实 API 调用（那些靠真实运行验证），用 fake platform 测平台相关逻辑。

用法：py -m pytest tests/test_monitor.py -v
  或： py tests/test_monitor.py
"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.monitor as monitor
from scripts.monitor import (
    fill_asks, evaluate_rung, is_valid_rt_data, should_watch,
    get_settle_date_for_mode, get_active_platforms,
)

TODAY = datetime(2026, 7, 15, tzinfo=timezone.utc)

PARAMS = {
    "DRIFT": 1.0, "PRIOR_STRENGTH": 20.0, "N_SIMS": 50000,
    "N_MIN": 10, "WIN_PROB_MIN": 0.80, "WIN_PROB_MAX": 0.95,
    "PRICE_MAX": 92, "EDGE_MIN": 5, "EDGE_MAX": 10,
    "SPREAD_MAX": 5, "N_FINAL": 200,
}


# ==================== fill_asks ====================

def test_fill_asks_single_level_enough():
    assert fill_asks([[45.0, 5000.0]], 100) == 45.0

def test_fill_asks_multi_level():
    assert fill_asks([[41.0, 50.0], [42.0, 50.0]], 100) == 41.5

def test_fill_asks_depth_insufficient():
    assert fill_asks([[41.0, 30.0], [42.0, 40.0]], 100) is None

def test_fill_asks_exact_depth():
    assert fill_asks([[40.0, 100.0]], 100) == 40.0

def test_fill_asks_empty():
    assert fill_asks([], 100) is None

def test_fill_asks_unsorted_input():
    # 乱序：排序后 40@60 + 50@40 = (2400+2000)/100 = 44.0
    assert fill_asks([[50.0, 60.0], [40.0, 60.0]], 100) == 44.0

def test_fill_asks_filters_nonpositive_size():
    assert fill_asks([[40.0, 0.0], [41.0, -5.0], [42.0, 100.0]], 100) == 42.0

def test_fill_asks_partial_last_level():
    assert fill_asks([[40.0, 60.0], [50.0, 100.0]], 100) == 44.0

def test_fill_asks_polymarket_garbage_order():
    # best价55先吃，99的垃圾单吃不到
    assert fill_asks([[55.0, 155.0], [99.0, 2000.0]], 100) == 55.0


# ==================== evaluate_rung ====================

def test_evaluate_rung_yes_opportunity():
    r = evaluate_rung(0.85, 78, 27, PARAMS)
    assert r is not None and r[0] == "YES" and abs(r[1] - 7.0) < 0.01

def test_evaluate_rung_no_opportunity():
    r = evaluate_rung(0.15, 27, 78, PARAMS)
    assert r is not None and r[0] == "NO" and abs(r[1] - 7.0) < 0.01

def test_evaluate_rung_spread_too_wide():
    assert evaluate_rung(0.85, 80, 30, PARAMS) is None

def test_evaluate_rung_edge_too_low():
    assert evaluate_rung(0.80, 78, 24, PARAMS) is None

def test_evaluate_rung_edge_too_high():
    assert evaluate_rung(0.90, 75, 23, PARAMS) is None

def test_evaluate_rung_winprob_too_low():
    assert evaluate_rung(0.70, 63, 20, PARAMS) is None

def test_evaluate_rung_winprob_too_high():
    assert evaluate_rung(0.98, 90, 8, PARAMS) is None

def test_evaluate_rung_price_too_high():
    assert evaluate_rung(0.95, 93, 5, PARAMS) is None

def test_evaluate_rung_boundary_edge_min():
    # edge正好5，价差5 → 命中
    r = evaluate_rung(0.85, 80, 25, PARAMS)
    assert r is not None and r[0] == "YES"

def test_evaluate_rung_boundary_winprob_min():
    r = evaluate_rung(0.80, 73, 32, PARAMS)
    assert r is not None and r[0] == "YES"

def test_evaluate_rung_direction_no_only():
    monitor.DIRECTION = "no_only"
    try:
        assert evaluate_rung(0.85, 78, 27, PARAMS) is None
    finally:
        monitor.DIRECTION = "both"

def test_evaluate_rung_direction_yes_only():
    monitor.DIRECTION = "yes_only"
    try:
        assert evaluate_rung(0.15, 27, 78, PARAMS) is None
    finally:
        monitor.DIRECTION = "both"


# ==================== is_valid_rt_data ====================

def test_valid_rt_data_normal():
    assert is_valid_rt_data(85, 120) is True

def test_valid_rt_data_none():
    assert is_valid_rt_data(None, 100) is False
    assert is_valid_rt_data(85, None) is False

def test_valid_rt_data_out_of_range():
    assert is_valid_rt_data(-5, 100) is False
    assert is_valid_rt_data(105, 100) is False

def test_valid_rt_data_negative_n():
    assert is_valid_rt_data(85, -3) is False

def test_valid_rt_data_zero_boundary():
    assert is_valid_rt_data(0, 50) is True
    assert is_valid_rt_data(100, 50) is True

def test_valid_rt_data_nonnumeric():
    assert is_valid_rt_data("abc", 100) is False
    assert is_valid_rt_data(85, "xyz") is False


# ==================== should_watch ====================

def test_should_watch_in_window():
    assert should_watch("2026-08-01", "2026-07-10", TODAY) is True

def test_should_watch_after_settle():
    assert should_watch("2026-07-10", None, TODAY) is False

def test_should_watch_before_embargo():
    assert should_watch("2026-08-01", "2026-07-20", TODAY) is False

def test_should_watch_lift_exactly_today():
    assert should_watch("2026-08-01", "2026-07-15", TODAY) is True

def test_should_watch_iso_format():
    assert should_watch("2026-08-01T14:00:00Z", None, TODAY) is True

def test_should_watch_string_none():
    assert should_watch("None", None, TODAY) is False

def test_should_watch_no_embargo():
    assert should_watch("2026-08-01", None, TODAY) is True


# ==================== get_settle_date_for_mode ====================

def test_settle_mode_kalshi_only():
    monitor.PLATFORM_MODE = "kalshi"
    try:
        cfg = {"kalshi_settle_date": "2026-08-10", "polymarket_settle_date": "2026-08-17"}
        assert get_settle_date_for_mode(cfg) == "2026-08-10"
    finally:
        monitor.PLATFORM_MODE = "kalshi"

def test_settle_mode_polymarket_only():
    monitor.PLATFORM_MODE = "polymarket"
    try:
        cfg = {"kalshi_settle_date": "2026-08-10", "polymarket_settle_date": "2026-08-17"}
        assert get_settle_date_for_mode(cfg) == "2026-08-17"
    finally:
        monitor.PLATFORM_MODE = "kalshi"

def test_settle_mode_both_takes_later():
    monitor.PLATFORM_MODE = "both"
    try:
        cfg = {"kalshi_settle_date": "2026-08-10", "polymarket_settle_date": "2026-08-17"}
        assert get_settle_date_for_mode(cfg) == "2026-08-17"
    finally:
        monitor.PLATFORM_MODE = "kalshi"

def test_settle_mode_polymarket_missing():
    monitor.PLATFORM_MODE = "polymarket"
    try:
        assert get_settle_date_for_mode({"kalshi_settle_date": "2026-08-10"}) == ""
    finally:
        monitor.PLATFORM_MODE = "kalshi"

def test_settle_mode_none_at_all():
    monitor.PLATFORM_MODE = "both"
    try:
        assert get_settle_date_for_mode({}) == ""
    finally:
        monitor.PLATFORM_MODE = "kalshi"


# ==================== get_active_platforms（两层过滤）====================

class FakePlatform:
    def __init__(self, name):
        self.name = name

def _patch_get_platforms(platforms):
    monitor.config.get_platforms = lambda cfg: platforms

def test_active_platforms_kalshi_mode():
    monitor.PLATFORM_MODE = "kalshi"
    orig = monitor.config.get_platforms
    try:
        _patch_get_platforms([FakePlatform("kalshi"), FakePlatform("polymarket")])
        active = get_active_platforms({})
        assert len(active) == 1 and active[0].name == "kalshi"
    finally:
        monitor.config.get_platforms = orig
        monitor.PLATFORM_MODE = "kalshi"

def test_active_platforms_polymarket_mode():
    monitor.PLATFORM_MODE = "polymarket"
    orig = monitor.config.get_platforms
    try:
        _patch_get_platforms([FakePlatform("kalshi"), FakePlatform("polymarket")])
        active = get_active_platforms({})
        assert len(active) == 1 and active[0].name == "polymarket"
    finally:
        monitor.config.get_platforms = orig
        monitor.PLATFORM_MODE = "kalshi"

def test_active_platforms_both_mode():
    monitor.PLATFORM_MODE = "both"
    orig = monitor.config.get_platforms
    try:
        _patch_get_platforms([FakePlatform("kalshi"), FakePlatform("polymarket")])
        assert len(get_active_platforms({})) == 2
    finally:
        monitor.config.get_platforms = orig
        monitor.PLATFORM_MODE = "kalshi"

def test_active_platforms_not_open_on_mode():
    monitor.PLATFORM_MODE = "polymarket"
    orig = monitor.config.get_platforms
    try:
        _patch_get_platforms([FakePlatform("kalshi")])
        assert get_active_platforms({}) == []
    finally:
        monitor.config.get_platforms = orig
        monitor.PLATFORM_MODE = "kalshi"

def test_active_platforms_none_open():
    monitor.PLATFORM_MODE = "both"
    orig = monitor.config.get_platforms
    try:
        _patch_get_platforms([])
        assert get_active_platforms({}) == []
    finally:
        monitor.config.get_platforms = orig
        monitor.PLATFORM_MODE = "kalshi"


# ==================== 平台规则差异 ====================

def test_platform_rule_difference():
    from src.model.bayesian import ModelInputs, run_model
    from src.collectors.platforms.kalshi import KalshiPlatform
    from src.collectors.platforms.polymarket import PolymarketPlatform
    res = run_model(ModelInputs(score_now=85, n_now=120, base_rate=80,
                                prior_strength=20, n_final=200, drift=1), n_sims=50000)
    assert PolymarketPlatform().yes_prob(res, 80) >= KalshiPlatform().yes_prob(res, 80)

def test_kalshi_yes_prob_uses_floor_plus_one():
    from src.model.bayesian import ModelInputs, run_model
    from src.collectors.platforms.kalshi import KalshiPlatform
    res = run_model(ModelInputs(score_now=85, n_now=120, base_rate=80,
                                prior_strength=20, n_final=200, drift=1), n_sims=50000)
    assert KalshiPlatform().yes_prob(res, 80) == res.prob_at_least(81)

def test_polymarket_yes_prob_uses_floor():
    from src.model.bayesian import ModelInputs, run_model
    from src.collectors.platforms.polymarket import PolymarketPlatform
    res = run_model(ModelInputs(score_now=85, n_now=120, base_rate=80,
                                prior_strength=20, n_final=200, drift=1), n_sims=50000)
    assert PolymarketPlatform().yes_prob(res, 80) == res.prob_at_least(80)


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for name, t in tests:
        try:
            t()
            print(f"OK {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'=' * 40}\n通过 {passed} / {passed + failed}")
    if failed:
        print(f"{failed} 个失败")
        sys.exit(1)
    print("全部通过")