"""
控制面板：放所有默认参数和你的电影清单。
这是整个项目里你最常改的文件——调参数、加电影、改价格，全在这里。
"""

from __future__ import annotations

# ===== 决策设置（对所有电影通用）=====
MIN_EDGE = 5.0     # 至少要有几美分的 edge 才行动（你的安全垫）。想激进就调低，想保守就调高。
WIN_FLOOR = 0.90   # "最稳健"推荐要求的最低胜率（0.90 = 90%）。

# ===== 模板阶梯 =====
# 加新电影时复制这个用。每一行是 (门槛, YES卖价, NO卖价)，单位美分。
# 不会被直接使用——每部电影在下面 WATCHLIST 里带自己的 "ladder"，
# 这样两部门槛/价格不同的片就不会互相干扰。
DEFAULT_LADDER = [
    (85, 97, 4),
    (88, 94, 7),
    (90, 89, 12),
    (92, 72, 29),
    (95, 38, 63),
]

# ===== 电影清单 =====
# 每部你想追踪的电影一个条目。
# 每部电影现在自带 "ladder"（门槛 + 当前 Kalshi 价格），所以价格按片各自更新。
# kalshi_event去kalshi网站上找这部电影对应的ticker代码，填在这里，就能拉实时价格了。
WATCHLIST = {
    # "toy_story_5" 是这部片的 key，你跑命令时 --movie toy_story_5 就用它。
    "toy_story_5": {
        "title": "Toy Story 5",
        "base_rate": 98.5,       # 系列历史均分（玩具总动员 1-4 都 97%+）
        "prior_strength": 15,  # ← 先验强度改这里
        "n_final": 280,        # 结算时预计评论数
        "drift": 2.0,          # ← 漂移改这里
        "kalshi_event": "KXRT-TOY",   # Toy Story 5 的 event ticker
        "kalshi_settle_date": "2026-06-22",  # Kalshi上的结算日期
        "rt_movie_id": "353d7ef9-2b59-4714-a3b6-c083b5508619",  # 这个 ID 告诉 fetch_reviews.py 去哪里抓评论
        "ladder": [
            # 门槛, YES卖价, NO卖价（美分）—— 改成实时市场价
            (89, 98, 2),
            (90, 95, 5),
            (91, 89, 12),
            (92, 72, 29),
            (95, 38, 63),
        ],
    },
    "the_death_of_robin_hood": {
        "title": "The Death of Robin Hood",
        "base_rate": 86,       
        "prior_strength": 8,  
        "n_final": 200,        
        "drift": 2.0,         
        "kalshi_event": "KXRT-DEA",   
        "kalshi_settle_date": "2026-06-22",
        "rt_movie_id": "749f12db-be4a-402b-9474-1d26b226f414",
        "ladder": [
            # 门槛, YES卖价, NO卖价（美分）—— 改成实时市场价
            (89, 98, 2),
            (90, 95, 5),
            (91, 89, 12),
            (92, 72, 29),
            (95, 38, 63),
        ],
    },
    # ===========================================================
    # ======================历史电影栏============================
    # ===========================================================
    "zootopia_2": {
    "title": "Zootopia 2",
    "base_rate": 90,       # TODO 待定，随便填，抓数据用不到
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTZOOTOPIA2",
    "kalshi_settle_date": "2025-12-01",   # 这个要准（网站查的）
    "rt_movie_id": "47d189ea-dcbd-3992-8cd0-86ff439aa52e", # 这个要准（F12查）
    },


    
    # 要加电影：复制上面整个 block，改 key 名和里面的值，
    # 并给它自己的 "ladder"（可以复制 DEFAULT_LADDER 当起点）。
}