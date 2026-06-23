"""
模型的健全性测试（sanity tests）。运行方法：  py -m pytest -q

这些测试复刻了我们当初在 React 原型上做的检查：
  - 小样本 => 分布更宽、P(>=90) 更低
  - 大样本 => 分布更窄、P(>=90) 更高
  - 做多和做空的胜率加起来等于 1
  - edge 的算术正确

pytest 会自动找到所有以 test_ 开头的函数并运行它们。
每个测试里用 assert（断言）：如果条件为假，测试就失败。
"""

from src.model.bayesian import ModelInputs, run_model
from src.strategy.decide import Rung, evaluate_ladder


def _inp(n_now):
    """辅助函数：造一个除了评论数以外都固定的输入，方便对比不同样本量。"""
    return ModelInputs(
        score_now=96, n_now=n_now, base_rate=97,
        prior_strength=15, n_final=250, drift=2.0,
    )


def test_sample_size_controls_spread():
    """验证：评论越多，对终值越确定。"""
    small = run_model(_inp(15))    # 只有 15 条评论
    large = run_model(_inp(120))   # 有 120 条评论
    # 评论越多 => 终值的不确定性(标准差)越小
    assert large.sd < small.sd
    # 而且更有把握超过 90%
    assert large.prob_at_least(90) > small.prob_at_least(90)


def test_yes_no_complement():
    """验证：做多胜率 + 做空胜率 = 1（因为是互补事件）。"""
    r = run_model(_inp(45))
    for t in (85, 90, 95):
        # abs(...) 取绝对值，< 1e-9 是说"几乎等于 0"（浮点数不能直接判等）
        assert abs(r.prob_at_least(t) + r.prob_below(t) - 1.0) < 1e-9


def test_mean_in_reasonable_range():
    """验证：96% / 45 条 / 强先验，终值应该落在 90 几。"""
    r = run_model(_inp(45))
    assert 90 < r.mean < 97


def test_edge_math():
    """验证：公平价和 edge 的算术没错。"""
    r = run_model(_inp(45))
    ladder = [Rung(t=90, yes_price=89, no_price=12)]
    e = evaluate_ladder(r, ladder)[0]   # [0] 取列表第一个元素
    assert abs(e.fair_yes - e.p_yes * 100) < 1e-9      # 公平价 = 概率 × 100
    assert abs(e.edge_yes - (e.fair_yes - 89)) < 1e-9  # 做多 edge = 公平价 - YES市价
    assert abs(e.edge_no - (e.fair_no - 12)) < 1e-9    # 做空 edge = 公平价 - NO市价