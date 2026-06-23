"""
模型核心：把"刚解禁时的烂番茄读数"变成"结算时刻最终分数的概率分布"。

这是整个项目的数学心脏。它不碰网络、不碰文件，纯粹是"输入数字 → 输出数字"，
所以可以被单独测试。

整条流水线（对应我们讨论过的原理七步）：
  1. 伯努利原子：每条影评要么 fresh(好评=1) 要么 rotten(差评=0)，好评概率为 p。
  2. 贝叶斯更新：把"当前 n 条里 k 条好评"和"系列历史先验"用 Beta 分布合并
     （Beta 是二项分布的共轭先验，算出来还是 Beta，形式封闭）。
  3. 漂移修正：早期影评人偏乐观，所以从 p 里减掉几个点。
  4. 蒙特卡洛：把两层不确定性（p 本身的不确定 + 未来评论的随机）模拟成终值分布。
"""

# 这行让旧版本 Python 也能用新式类型注解（比如 int | None 这种写法）
from __future__ import annotations

# dataclass 是一个方便的工具，能让我们少写很多样板代码就定义一个"数据容器"类
from dataclasses import dataclass

# numpy 是 Python 做数值计算的标准库，这里用它做大规模随机抽样和数组运算
import numpy as np


# @dataclass 装饰器：自动帮这个类生成 __init__ 等方法。
# 你只要列出字段名和类型，就能用 ModelInputs(score_now=96, ...) 来创建对象。
@dataclass
class ModelInputs:
    """模型的所有输入，全都是你在 embargo 解禁时能查到的数值。"""

    score_now: float       # 此刻显示的烂番茄分数 %，例如 96
    n_now: int             # 这个分数基于多少条影评，例如 45（最关键的输入）
    base_rate: float       # 系列/导演的历史平均烂番茄分 %，例如 97（进先验）
    prior_strength: float  # 对先验的信任度，用"伪评论数"衡量，例如 15
    n_final: int           # 预计结算时会有多少条影评，例如 250
    drift: float           # 早期乐观偏差，要减掉的点数，例如 2.0


@dataclass
class ModelResult:
    """模型输出：终值分布，外加几个查询概率的辅助方法。"""

    mean: float                 # 模拟出的终值的平均数 %
    sd: float                   # 标准差（1 个 sigma，单位是"点"），衡量不确定性大小
    final_scores: np.ndarray    # 所有模拟出来的终值组成的数组（几十万个数）

    # 下面两个是"方法"——定义在类里面的函数，第一个参数 self 指对象自己。
    def prob_at_least(self, threshold: float) -> float:
        """P(终值 >= 门槛)，也就是做多(买 YES)的获胜概率。"""
        # final_scores >= threshold 会得到一个布尔数组(True/False)，
        # np.mean 把 True 当 1、False 当 0 求平均，结果正好就是"占比" = 概率。
        return float(np.mean(self.final_scores >= threshold))

    def prob_below(self, threshold: float) -> float:
        """P(终值 < 门槛)，也就是做空(买 NO)的获胜概率。"""
        return float(np.mean(self.final_scores < threshold))


def run_model(inp: ModelInputs, n_sims: int = 200_000, seed: int | None = 42) -> ModelResult:
    """
    跑蒙特卡洛模拟，返回终值分布。

    n_sims: 模拟多少个"平行世界"。20 万次能让概率稳定到小数点后约 2 位。
    seed:   随机种子。固定它能让每次运行结果一致（方便调试）；传 None 则每次都不同。
    """
    # 创建一个随机数生成器。给定 seed，它产生的随机序列就是可复现的。
    rng = np.random.default_rng(seed)

    # --- 已经锁定的好评数 ---
    # 当前分数 × 评论数 = 好评条数。round 四舍五入成整数。
    # 这里算出现在已经解禁后的真实好评数量
    k = round(inp.score_now / 100 * inp.n_now)

    # --- 把先验表达成"伪好评数 / 伪差评数" ---
    # 比如 base_rate=97、prior_strength=15，相当于"假装提前见过 15 条评论，
    # 其中 97% 是好评"，即约 14.55 条好评、0.45 条差评。
    # 这里算贝叶斯先验的参数，a0 是好评侧的伪计数，b0 是差评侧的伪计数。
    a0 = inp.base_rate / 100 * inp.prior_strength
    b0 = (1 - inp.base_rate / 100) * inp.prior_strength

    # --- 真实好评概率 p 的 Beta 后验 ---
    # 共轭更新规则极简单：后验参数 = 先验伪计数 + 实际观测计数。
    # 这里计算beta后验的参数，a 是好评侧的总计数，b 是差评侧的总计数。
    a = a0 + k                 # 好评侧
    b = b0 + (inp.n_now - k)   # 差评侧

    # 第一层不确定性：从后验分布里抽 p。每个平行世界抽一个不同的 p。
    # 相当于开了20万个平行宇宙，对于每一个宇宙抽样一次，得到一个p，然后p_samples就是20万个宇宙的所有p值。
    p_samples = rng.beta(a, b, size=n_sims)

    # 漂移修正：早期影评人偏乐观，所以把 p 往下调 drift 个点。
    # np.clip 把结果限制在 [0.001, 0.999]，避免出现 0 或 1 这种极端值。
    # 先把p_samles里每个p都减去漂移值（转换成小数），再限制在0.001到0.999之间，得到调整后的p_adj。
    # np.clip(..., 0.001, 0.999)：这是一个“安全裁剪”函数。
    # 它规定：减完之后，如果某个宇宙的概率不幸跌破了 0.001（0.1%），就强行让它等于 0.001；
    # 如果涨破了 0.999（99.9%），就强行等于 0.999
    p_adj = np.clip(p_samples - inp.drift / 100, 0.001, 0.999)

    # 第二层不确定性：还没出现的评论，是按 p_adj 概率的二项抽样。
    # 先用n_final减去n_now算出还会增加多少条评论
    n_remaining = max(inp.n_final - inp.n_now, 0)   # 还会新增多少条评论

    # 这一步模拟n_remaining条评论里有多少条好评
    # 给刚才-drift修正后的20万个p都分别模拟一次二项分布，得到20万个宇宙里新增评论的好评数。
    # 例如第一号宇宙中修正后的p_adj是0.85，n_remaining是100，然后做抛硬币,
    # 每次正面概率是0.85，抛100次，统计正面朝上的次数，就是这个宇宙中的真实好评数量，
    # 然后以此类推，把20万个p_adj都模拟一次，得到了20万个真实好评数量，存进new_fresh这个数组里。
    new_fresh = rng.binomial(n_remaining, p_adj)    # 这些新评论里有多少好评

    # 这一步将现有的公布在烂番茄上的真实好评数量+刚才模拟的好评数量，得到每个宇宙中的终值好评数量。
    final_fresh = k + new_fresh                      # 终值好评总数 = 已锁定 + 新增

    # 然后再除以总评论数换算成百分比的好评率
    # 得到一个包含 20 万个分数的数组（比如 [94.5, 96.2, 91.8, ...]）。
    final_scores = final_fresh / inp.n_final * 100   # 换算成百分比

    # 把结果打包成 ModelResult 返回。.mean()/.std() 是 numpy 数组自带的求均值/标准差。
    return ModelResult(
        mean=float(final_scores.mean()), # 对20万个结果求平均数
        sd=float(final_scores.std()), # 算出这 20 万个得分的标准差（每一个数平均下来距离平均数有多远）
        final_scores=final_scores,
    )