"""
决策层：拿模型给出的终值分布 + Kalshi 各档价格，算出每个门槛的
做多(买 YES)和做空(买 NO) edge，再挑出每一边"最稳健"和"最佳价值"的推荐。

定价逻辑（单位：美分 cents）：
  做多公平价 = P(终值 >= 门槛) * 100      做多 edge = 做多公平价 - YES 市价
  做空公平价 = P(终值 <  门槛) * 100      做空 edge = 做空公平价 - NO  市价
  edge > 0  =>  合约被低估  =>  正期望值，值得买。
"""

from __future__ import annotations

from dataclasses import dataclass

# 从模型层导入 ModelResult，这样这里能用它的 prob_at_least 等方法。
from src.model.bayesian import ModelResult


@dataclass
class Rung:
    """Kalshi 阶梯上的一档（一个门槛），带它当前的市场价格。"""

    t: float          # 门槛，例如 90 表示 "above 90%"
    yes_price: float  # YES(above) 的卖价（美分）
    no_price: float   # NO(below)  的卖价（美分）


@dataclass
class RungEval:
    """一档经过模型打分之后的完整结果（做多、做空两边都算好）。"""

    t: float
    # 做多 / YES 一侧
    p_yes: float      # 做多获胜概率
    fair_yes: float   # 做多公平价
    yes_price: float  # YES 市价
    edge_yes: float   # 做多 edge = 公平价 - 市价
    # 做空 / NO 一侧
    p_no: float       # 做空获胜概率
    fair_no: float    # 做空公平价
    no_price: float   # NO 市价
    edge_no: float    # 做空 edge


def evaluate_ladder(result: ModelResult, ladder: list[Rung]) -> list[RungEval]:
    """对阶梯上的每一档，在做多和做空两侧都打分。"""
    out: list[RungEval] = []   # 先准备一个空列表，循环里往里塞结果
    for r in ladder:           # 遍历每一档
        p_yes = result.prob_at_least(r.t)   # 终值 >= 门槛的概率
        p_no = 1.0 - p_yes                  # 做空获胜概率 = 1 - 做多获胜概率
        fair_yes = p_yes * 100              # 概率换算成美分就是公平价
        fair_no = p_no * 100
        # 把这一档的所有计算结果打包成 RungEval，追加进列表
        out.append(
            RungEval(
                t=r.t,
                p_yes=p_yes,
                fair_yes=fair_yes,
                yes_price=r.yes_price,
                edge_yes=fair_yes - r.yes_price,   # 做多 edge
                p_no=p_no,
                fair_no=fair_no,
                no_price=r.no_price,
                edge_no=fair_no - r.no_price,       # 做空 edge
            )
        )
    return out


@dataclass
class Picks:
    """模型在每一边给出的推荐（任何一个都可能是 None，表示"这边没机会，放弃"）。"""

    robust_long: RungEval | None    # 最稳健做多
    best_long: RungEval | None      # 最佳价值做多
    robust_short: RungEval | None   # 最稳健做空
    best_short: RungEval | None     # 最佳价值做空


def choose(
    evals: list[RungEval],
    min_edge: float = 5.0,
    win_floor: float = 0.90,
) -> Picks:
    """
    应用选股规则：

    做多·稳健 ：在"胜率 >= win_floor 且 edge >= min_edge"的档里，选门槛最高的。
    做多·价值 ：在所有"edge >= min_edge"的档里，选 edge 最大的。
    做空·稳健 ：在"NO 胜率 >= win_floor 且 edge >= min_edge"的档里，选门槛最低的。
                （门槛越低，NO 越难赢，所以最低的安全档就是最激进的稳健空单）
    做空·价值 ：在所有"做空 edge >= min_edge"的档里，选 edge 最大的。
    """
    # 列表推导式：[x for x in 列表 if 条件]，意思是"挑出满足条件的元素组成新列表"。
    # 这一行挑出所有"做多胜率够高且 edge 够大"的档。
    long_ok = [e for e in evals if e.p_yes >= win_floor and e.edge_yes >= min_edge]
    # max(..., key=取哪个字段比大小, default=都没有时返回啥)
    # 在符合条件的档里选 t（门槛）最大的那个。如果 long_ok 为空就返回 None。
    robust_long = max(long_ok, key=lambda e: e.t, default=None)

    long_edge_ok = [e for e in evals if e.edge_yes >= min_edge]
    best_long = max(long_edge_ok, key=lambda e: e.edge_yes, default=None)

    short_ok = [e for e in evals if e.p_no >= win_floor and e.edge_no >= min_edge]
    # 注意做空稳健用的是 min（选门槛最低的），和做多相反。
    robust_short = min(short_ok, key=lambda e: e.t, default=None)

    short_edge_ok = [e for e in evals if e.edge_no >= min_edge]
    best_short = max(short_edge_ok, key=lambda e: e.edge_no, default=None)

    return Picks(
        robust_long=robust_long,
        best_long=best_long,
        robust_short=robust_short,
        best_short=best_short,
    )