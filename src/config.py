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
        "base_rate": 98,  # base_rate=98: 玩具总动员 1-4 均分（直系前作，全系列 97%+）
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
        "base_rate": 60,  # base_rate=60: 无前作；导演 Michael Sarnoski（A Quiet Place: Day One ~85, Pig ~96）风格文艺，但罗宾汉黑暗改编题材不确定，取中性剧情/动作带"prior_strength": 8,  
        "n_final": 200,        
        "drift": 2.0,         
        "kalshi_event": "KXRT-DEA",   
        "kalshi_settle_date": "2026-06-22",
        "final_score_official": 70,
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
    # =================历史电影栏(Kalshi开过盘的)==================
    # ===========================================================
    "young_washington": {
        "embargo_date": "2026-06-29",
    "title": "Young Washington",
    "base_rate": 60,  # base_rate=60: 无前作；历史传记剧情片类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-YOUN",
    "kalshi_settle_date": "2026-07-06",   # 这个要准（网站查的）
    "final_score_official": 60,   # Kalshi 结算时官方认定的最终 RT 分数（网站查，手动记）
    "rt_movie_id": "97baf9df-1d59-4eb9-a47c-98107c786e61", # 这个要准（F12查）
    },

    "minions_and_monsters": {
        "embargo_date": "2026-06-22",
    "title": "Minions & Monsters",
    "base_rate": 70,  # base_rate=70: 神偷奶爸/小黄人系列水位（Minions ~54, Rise of Gru ~70），照明娱乐动画品控
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTCAPTAINAMERICA",
    "kalshi_settle_date": "2026-07-06",   
    "final_score_official": 51,   
    "rt_movie_id": "2b250e14-f43a-3704-92bf-efe317a75f0c", 
    },

    "jackass_best_and_last": {
    "title": "Jackass: Best and Last",
    "base_rate": 80,  # base_rate=80: Jackass 系列均分（前作普遍 60-85%，Forever ~85）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-JAC",
    "kalshi_settle_date": "2026-06-29",   
    "final_score_official": 88,   
    "rt_movie_id": "db496dd5-0978-3f95-a391-973bd54d0538", 
    },

    "girls_like_girls": {
    "title": "Girls Like Girls",
    "base_rate": 70,  # base_rate=70: 无前作；青少年 LGBTQ 剧情独立片类型均分
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-GIR",
    "kalshi_settle_date": "2026-06-22",   
    "final_score_official": 89,   
    "rt_movie_id": "2a7ea75b-c01b-4a82-8476-6ac3b0495f30", 
    },

    "stop_that_train": {
        "embargo_date": "2026-06-09",
    "title": "Stop! That! Train!",
    "base_rate": 65,  # base_rate=65: 无前作小片；剧情/惊悚类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-STO",
    "kalshi_settle_date": "2026-06-15",   
    "final_score_official": 84,   
    "rt_movie_id": "ff2ccab7-7fc2-341b-8055-d0874c5ed659", 
    },

    "obsession": {
    "title": "Obsession",
    "base_rate": 45,  # base_rate=45: 惊悚/情色惊悚类型历史均分（该子类型口碑普遍偏低）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-OBS",
    "kalshi_settle_date": "2026-05-18",   
    "final_score_official": 94,   
    "rt_movie_id": "ba9968a1-a138-4b9e-9b70-322d06b9a667", 
    "exclude_from_backtest": True,
    },

    "supergirl": {
    "title": "Supergirl",
    "base_rate": 62,  # base_rate=62: 同 DC/新版 DCU 超英片水位（近期 DC 品控波动，取中性超英带）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SUPE",
    "kalshi_settle_date": "2026-06-29",   
    "final_score_official": 56,   
    "rt_movie_id": "62081606-2dbc-38f8-9650-a786c8128960", 
    },

    "scary_movie": {
    "title": "Scary Movie",
    "base_rate": 50,  # base_rate=50: Scary Movie 系列均分（1 ~53, 后续跌至 30-40），恶搞喜剧类型
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SCA",
    "kalshi_settle_date": "2026-06-08",   
    "final_score_official": 24,   
    "rt_movie_id": "a8a513c9-ea6a-371b-acd4-0808fd9ae668", 
    },

    "masters_of_the_universe": {
    "title": "Masters of the Universe",
    "base_rate": 55,  # base_rate=55: 无强前作；玩具改编大片/动作奇幻类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-MAS",
    "kalshi_settle_date": "2026-06-08",   
    "final_score_official": 66,   
    "rt_movie_id": "4b407cab-57e7-3658-9cf9-e03e85ecb4a6", 
    },

    "power_ballad": {
    "title": "Power Ballad",
    "base_rate": 65,  # base_rate=65: 无前作；音乐喜剧类型历史均分
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-POW",
    "kalshi_settle_date": "2026-06-08",   
    "final_score_official": 86,   
    "rt_movie_id": "12325ae1-e403-455d-8974-f8e30f61a470", 
    },

    "backrooms": {
    "title": "Backrooms",
    "base_rate": 60,  # base_rate=60: 无前作；网络恐怖 IP 改编，恐怖类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-BAC",
    "kalshi_settle_date": "2026-06-01",   
    "final_score_official": 89,   
    "rt_movie_id": "d31d9627-4451-41bb-a177-6ef5baf449e7", 
    },

    "billie_eilish_hit_me_hard_and_soft": {
    "title": "Billie Eilish - Hit Me Hard and Soft: The Tour (Live in 3D)",
    "base_rate": 90,  # base_rate=90: 演唱会纪录片类型（此类片 RT 普遍很高，85-95）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-BIL",
    "kalshi_settle_date": "2026-05-11",   
    "final_score_official": 93,   
    "rt_movie_id": "71059d17-d3f6-34c2-981c-f2a6d0f27bea", 
    },

    "in_the_grey": {
        "embargo_date": "2026-05-13",
    "title": "In the Grey",
    "base_rate": 60,  # base_rate=60: 无前作；导演 Guy Ritchie 近期作品波动大（Covenant ~83, Wrath of Man ~68, Fortune ~55），动作片取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-INT",
    "kalshi_settle_date": "2026-05-18",   
    "final_score_official": 46,   
    "rt_movie_id": "5deec4e1-def7-3c57-bad4-7eee17efe3fe", 
    },

    "the_sheep_detectives": {
    "title": "The Sheep Detectives",
    "base_rate": 78,  # base_rate=78: 无前作；家庭动画/定格类型均分（此类小成本动画口碑偏高）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SHEE",
    "kalshi_settle_date": "2026-05-11",   
    "final_score_official": 93,   
    "rt_movie_id": "0585bee6-1a2b-416f-a555-b3330799f245", 
    },

    "animal_farm": {
    "title": "Animal Farm",
    "base_rate": 65,  # base_rate=65: 无前作新改编；动画寓言类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-ANI",
    "kalshi_settle_date": "2026-05-04",   
    "final_score_official": 24,   
    "rt_movie_id": "5362e30c-342a-4ba7-858a-56dbfc7341b6", 
    "exclude_from_backtest": True,
    },

    "lee_cronin_the_mummy": {
    "title": "Lee Cronin's The Mummy",
    "base_rate": 70,  # base_rate=70: 无直系前作；导演 Lee Cronin（Evil Dead Rise ~85）近作 + 恐怖类型
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-LEE",
    "kalshi_settle_date": "2026-04-20",   
    "final_score_official": 46,   
    "rt_movie_id": "55a5dcec-ee67-3fb7-8dde-702335db916a", 
    },

    "the_devil_wears_prada_2": {
    "title": "The Devil Wears Prada 2",
    "base_rate": 75,  # base_rate=75: 前作《穿普拉达的女王》(2006) ~75%，直系续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-DEV",
    "kalshi_settle_date": "2026-05-04",   
    "final_score_official": 77,   
    "rt_movie_id": "b1750c91-9b2c-3be6-9ac4-bd8a4ecdf370", 
    },

    "mother_mary": {
    "title": "Mother Mary",
    "base_rate": 68,  # base_rate=68: 无前作；导演 David Lowery 近作（Green Knight ~85, Peter Pan ~62），音乐剧情取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-MOT",
    "kalshi_settle_date": "2026-04-27",   
    "final_score_official": 68,   
    "rt_movie_id": "a56be5b5-fd75-4569-aa98-f1a242f5ffe9", 
    },
    
    "zootopia_2": {
    "title": "Zootopia 2",
    "base_rate": 90,  # base_rate=90: 疯狂动物城 1 (~98)，迪士尼动画续集通常略降，取保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTZOOTOPIA2",
    "kalshi_settle_date": "2025-12-01",   # 这个要准（网站查的）
    "final_score_official": 91,   # Kalshi 结算时官方认定的最终 RT 分数（网站查，手动记）
    "rt_movie_id": "47d189ea-dcbd-3992-8cd0-86ff439aa52e", # 这个要准（F12查）
    },

    "avatar_fire_and_ash": {
        "embargo_date": "2025-12-16",
    "title": "Avatar: Fire And Ash",
    "base_rate": 80,  # base_rate=80: 阿凡达 1-2 均分（~81, ~76 后升），虽然卡梅隆品控强,但比所有前作都高需要理由。建议往前作均分靠,80左右更稳
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTAVATARFIREANDASH",
    "kalshi_settle_date": "2025-12-22",   
    "final_score_official": 67,   
    "rt_movie_id": "abb14eda-5add-3f6b-b99b-a54bef33235c", 
    },

    "captain_america_brave_new_world": {
    "title": "Captain America: Brave New World",
    "base_rate": 68,  # base_rate=68: 美队系列 + 近期漫威 MCU 阶段水位（品控下滑，取中性超英带）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTCAPTAINAMERICA",
    "kalshi_settle_date": "2025-02-17",   
    "final_score_official": 51,   
    "rt_movie_id": "352f98e6-072f-3c43-b2da-8b4b38ba7fe9", 
    },

    "moana_2": {
    "title": "Moana 2",
    "base_rate": 76,  # base_rate=76: 海洋奇缘 1 (~95)，但续集从剧集改制、迪士尼近期续集普遍降，取保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTMOANA2",
    "kalshi_settle_date": "2024-12-02",   
    "final_score_official": 65,   
    "rt_movie_id": "4f945245-5bc5-3121-abf2-2b23228ac6ec", 
    },

    "michael": {
    "title": "Michael",
    "base_rate": 65,  # base_rate=65: 无前作；音乐传记片类型均分（此类片口碑波动大）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-MIC",
    "kalshi_settle_date": "2026-04-27",   
    "final_score_official": 38,   
    "rt_movie_id": "a23a9daf-6236-4468-bdc9-39777d52d75b", 
    },

    "mickey_17": {
    "title": "Mickey 17",
    "base_rate": 88,  # base_rate=88: 导演奉俊昊近作（寄生虫 ~99, 玉子 ~85, 雪国列车 ~94）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTMICKEY17",
    "kalshi_settle_date": "2025-03-10",   
    "final_score_official": 78,   
    "rt_movie_id": "843f6299-c24a-430a-b24f-b3bb6c009dfb", 
    },

    "disney_snow_white": {
    "title": "Disney's Snow White",
    "base_rate": 60,  # base_rate=60: 迪士尼真人翻拍近期水位（Little Mermaid ~67, Pinocchio ~27, Mulan ~73），取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTSNOWWHITE",
    "kalshi_settle_date": "2025-03-24",   
    "final_score_official": 44,   
    "rt_movie_id": "50fc9222-cd08-46a5-a4c5-d3e6e0aedb49", 
    },

    "project_hail_mary": {
    "title": "Project Hail Mary",
    "base_rate": 82,  # base_rate=82: 导演 Lord & Miller（Spider-Verse ~94-95, 21 Jump St ~85），科幻改编取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-PRO",
    "kalshi_settle_date": "2026-03-23",   
    "final_score_official": 95,   
    "rt_movie_id": "5c4afb29-9a25-4fac-9a1c-b6a4528b7935", 
    },

    "mufasa": {
    "title": "Mufasa",
    "base_rate": 62,  # base_rate=62: 狮子王真人版 (2019) ~52，迪士尼前传/翻拍水位，略调高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTMUFASA",
    "kalshi_settle_date": "2024-12-23",   
    "final_score_official": 56,   
    "rt_movie_id": "9786dfef-6bec-4797-a07f-c4c8e85b4e68", 
    },

    "a_minecraft_movie": {
    "title": "A Minecraft Movie",
    "base_rate": 55,  # base_rate=55: 无前作；游戏改编电影类型均分兜底（波动大）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTMINECRAFT",
    "kalshi_settle_date": "2025-04-07",   
    "final_score_official": 47,   
    "rt_movie_id": "99fb8537-d488-345c-864f-7f5216634809", 
    },

    "wicked_for_good": {
    "title": "Wicked: For Good",
    "base_rate": 88,  # base_rate=88: 前作 Wicked (2024) ~88，直系续集（同拍摄、同班底）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWICKEDFORGOOD",
    "kalshi_settle_date": "2025-11-24",   
    "final_score_official": 70,   
    "rt_movie_id": "37521ff5-0423-314e-812d-7d89d8118496", 
    },

    "the_monkey": {
        "embargo_date": "2025-02-21",
    "title": "The Monkey",
    "base_rate": 78,  # base_rate=78: 导演 Osgood Perkins（Longlegs ~86），恐怖类型近作
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHEMONKEY",
    "kalshi_settle_date": "2025-02-24",   
    "final_score_official": 78,   
    "rt_movie_id": "28015cc1-f708-3499-92a3-3a6fc3c3af36", 
    },

    "disclosure_day": {
    "title": "Disclosure Day",
    "base_rate": 60,  # base_rate=60: 无信息；剧情/惊悚类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-DIS",
    "kalshi_settle_date": "2026-06-15",   
    "final_score_official": 80,   
    "rt_movie_id": "0e72bf7d-41ad-434c-af9e-85134db1d77c", 
    },

    "the_super_mario_galaxy_movie": {
    "title": "The Super Mario Galaxy Movie",
    "base_rate": 60,  # base_rate=60: 前作 Super Mario Bros Movie (2023) ~59，直系续集（照明+任天堂）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SUP",
    "kalshi_settle_date": "2026-04-06",   
    "final_score_official": 42,   
    "rt_movie_id": "302eba7f-d168-4a8a-9f72-98d4a9b91418", 
    },

    "wicked": {
    "title": "Wicked",
    "base_rate": 78,  # base_rate=78: 无前作电影；导演 Jon M. Chu（Crazy Rich Asians ~91, In the Heights ~94, Jem ~20），歌舞片取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWICKED",
    "kalshi_settle_date": "2024-11-25",   
    "final_score_official": 90,   
    "rt_movie_id": "0fb0ec41-5919-34d5-8731-0c6254471412", 
    },

    "novocaine": {
        "embargo_date": "2025-03-08",
    "title": "Novocaine",
    "base_rate": 68,  # base_rate=68: 无前作；动作喜剧类型历史均分
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTNOVOCAINE",
    "kalshi_settle_date": "2025-03-17",   
    "final_score_official": 82,   
    "rt_movie_id": "ce3ce860-c7d0-4ea7-9b21-ed1faf75e3ff", 
    },

    "the_fantastic_four_first_steps": {
    "title": "The Fantastic Four: First Steps",
    "base_rate": 65,  # base_rate=65: 神奇四侠历史普遍低（前作 ~27, ~9），但新 MCU 重启 + 好导演，大幅调高至中性超英带
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTFANTASTICFOUR",
    "kalshi_settle_date": "2025-07-28",   
    "final_score_official": 87,   
    "rt_movie_id": "db64beee-683b-39ce-9617-94f6b67aa997", 
    },

    "star_wars_the_mandalorian_and_grogu": {
    "title": "Star Wars: The Mandalorian and Grogu",
    "base_rate": 80,  # base_rate=80: 曼达洛人剧集口碑极高 + 星战电影近期水位，取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-STA",
    "kalshi_settle_date": "2026-05-25",   
    "final_score_official": 62,   
    "rt_movie_id": "efc79510-0afa-3f89-a3a1-348a5d84875c", 
    },

    "mortal_kombat_ii": {
    "title": "Mortal Kombat II",
    "base_rate": 50,  # base_rate=50: 前作 Mortal Kombat (2021) ~55，游戏改编续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-MOR",
    "kalshi_settle_date": "2026-05-11",   
    "final_score_official": 66,   
    "rt_movie_id": "94e1d509-39a2-4c9b-8ca8-ef6ea6e92c39", 
    },

    "nosferatu": {
    "title": "Nosferatu",
    "base_rate": 85,  # base_rate=85: 导演 Robert Eggers（The Witch ~90, The Lighthouse ~90, The Northman ~89）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTNOSFERATU",
    "kalshi_settle_date": "2024-12-30",   
    "final_score_official": 86,   
    "rt_movie_id": "2112ebcf-e450-360a-9c19-9d2fbdb681e4", 
    },

    "28_years_later_the_bone_temple": {
    "title": "28 Years Later: The Bone Temple",
    "base_rate": 82,  # base_rate=82: 前作 28 Years Later (~88) + 28 系列，导演 Nia DaCosta 接手，略降
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT28YEARSLATERTBT",
    "kalshi_settle_date": "2026-01-19",   
    "final_score_official": 93,   
    "rt_movie_id": "8261c2a0-972c-4830-91ce-e625d1dba0dd", 
    },
    
    "superman": {
    "title": "Superman",
    "base_rate": 78,  # base_rate=78: 导演 James Gunn（银河护卫队 ~85-93, Suicide Squad ~90），新 DCU 开篇取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTSUPERMAN",
    "kalshi_settle_date": "2025-7-14",   
    "final_score_official": 83,   
    "rt_movie_id": "14bf945a-56c8-352b-ad53-0fa0bcab9051", 
    },

    "the_drama": {
    "title": "The Drama",
    "base_rate": 68,  # base_rate=68: 无前作；导演 Kristoffer Borgli（Sick of Myself ~95, Dream Scenario ~91），A24 取中高但题材未知，保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-DRA",
    "kalshi_settle_date": "2026-04-06",   
    "final_score_official": 77,   
    "rt_movie_id": "a3fa0192-8eaf-3803-8da0-7623d69c602a", 
    },

    "ready_or_not_2_here_i_come": {
    "title": "Ready or Not 2: Here I Come",
    "base_rate": 88,  # base_rate=88: 前作 Ready or Not (2019) ~88，同 Radio Silence 班底续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-REA",
    "kalshi_settle_date": "2026-03-23",   
    "final_score_official": 75,   
    "rt_movie_id": "ba0ab3d6-fa0d-41fb-963a-0ee5ee5cf378", 
    },

    "forbidden_fruits": {
        "embargo_date": "2026-03-16",
    "title": "Forbidden Fruits",
    "base_rate": 65,  # base_rate=65: 无信息；剧情类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-FRO",
    "kalshi_settle_date": "2026-03-30",   
    "final_score_official": 79,   
    "rt_movie_id": "345c59a2-524e-4675-869c-20b990bc9366", 
    },

    "reminders_of_him": {
    "title": "Reminders of Him",
    "base_rate": 55,  # base_rate=55: 无前作；Colleen Hoover 小说改编爱情剧情（此类改编影评普遍偏低）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-REM",
    "kalshi_settle_date": "2026-03-16",   
    "final_score_official": 56,   
    "rt_movie_id": "a76e677e-4a14-44d7-91b3-25197c7a650e", 
    },

    "hoppers": {
    "title": "Hoppers",
    "base_rate": 78,  # base_rate=78: 皮克斯原创动画，皮克斯质量带（原创片近期 ~75-95）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-HOP",
    "kalshi_settle_date": "2026-03-09",   
    "final_score_official": 94,   
    "rt_movie_id": "82089a16-ee83-4b30-8da7-ba10e40c04dd", 
    },

    "the_bride": {
    "title": "The Bride!",
    "base_rate": 65,  # base_rate=65: 无前作；导演 Maggie Gyllenhaal（The Lost Daughter ~95），但怪物大片题材不确定，取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-BRI",
    "kalshi_settle_date": "2026-03-09",   
    "final_score_official": 59,   
    "rt_movie_id": "0743b154-b563-4188-aa0d-a48ebc914e95", 
    },

    "scream_7": {
    "title": "Scream 7",
    "base_rate": 72,  # base_rate=72: 惊声尖叫系列均分（近作 Scream 2022 ~76, VI ~76），恐怖续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SCR",
    "kalshi_settle_date": "2026-03-02",   
    "final_score_official": 32,   
    "rt_movie_id": "3330029f-0135-30b7-8ccc-0c0af90d16dc", 
    },

    "how_to_make_a_killing": {
    "title": "How to Make a Killing",
    "base_rate": 65,  # base_rate=65: 无信息；犯罪/惊悚喜剧类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-HOW",
    "kalshi_settle_date": "2026-02-23",   
    "final_score_official": 49,   
    "rt_movie_id": "a2c3f500-8d8e-42c4-889d-a69cdcb057a5", 
    },

    "mercy": {
    "title": "Mercy",
    "base_rate": 60,  # base_rate=60: 无信息；剧情/惊悚类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-MER",
    "kalshi_settle_date": "2026-01-26",   
    "final_score_official": 21,   
    "rt_movie_id": "b506861e-4baa-30da-b745-40fa5a1103ea", 
    },

    "crime_101": {
    "title": "Crime 101",
    "base_rate": 70,  # base_rate=70: 无前作；导演 Bart Layton（American Animals ~88），犯罪片取中高但阵容未知，保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-CRI",
    "kalshi_settle_date": "2026-02-16",   
    "final_score_official": 86,   
    "rt_movie_id": "a1b90fda-d8b7-4e3e-a8ac-68877e8cc75e", 
    },

    "wuthering_heights": {
    "title": "Wuthering Heights",
    "base_rate": 68,  # base_rate=68: 无前作；导演 Emerald Fennell（Promising Young Woman ~90, Saltburn ~71），文学改编取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-WUT",
    "kalshi_settle_date": "2026-02-16",   
    "final_score_official": 61,   
    "rt_movie_id": "02331ca8-9f17-4098-ab08-d90bc8a68926", 
    },

    "the_strangers_chapter_3": {
    "title": "The Strangers – Chapter 3",
    "base_rate": 20,  # base_rate=20: 前作 The Strangers: Chapter 1 (2024) ~19，同三部曲续集，恐怖类型
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-STR",
    "kalshi_settle_date": "2026-02-09",   
    "final_score_official": 17,   
    "rt_movie_id": "21979eed-865b-3e8c-b106-1e8cf50d9ee5", 
    },

    "whistle": {
    "title": "Whistle",
    "base_rate": 55,  # base_rate=55: 无信息；恐怖类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-WHI",
    "kalshi_settle_date": "2026-02-09",   
    "final_score_official": 61,   
    "rt_movie_id": "6aecc3ba-e804-4de6-b79f-4581bbc1eec4", 
    "exclude_from_backtest": True,
    },

    "melania": {
    "title": "Melania",
    "base_rate": 40,  # base_rate=40: 无前作；名人传记纪录片（政治题材，此类片口碑两极且偏低）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-MEL",
    "kalshi_settle_date": "2026-02-02",   
    "final_score_official": 10,   
    "rt_movie_id": "a7a5829a-1623-3fc4-b582-2cfd0b7293b0", 
    },

    "shelter": {
    "title": "Shelter",
    "base_rate": 60,  # base_rate=60: 无信息；剧情/惊悚类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SHE",
    "kalshi_settle_date": "2026-02-02",   
    "final_score_official": 65,   
    "rt_movie_id": "753d8794-6af4-4822-8741-1027dc7cb9fd", 
    },

    "send_help": {
    "title": "Send Help",
    "base_rate": 62,  # base_rate=62: 无前作；导演 Sam Raimi 惊悚喜剧近作方向，取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SEN",
    "kalshi_settle_date": "2026-02-02",   
    "final_score_official": 93,   
    "rt_movie_id": "cb03f933-540f-3325-a619-ae59036c111e", 
    },

    "primate": {
    "title": "Primate",
    "base_rate": 58,  # base_rate=58: 无前作；动物恐怖/惊悚类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTPRIMATE",
    "kalshi_settle_date": "2026-01-12",   
    "final_score_official": 77,   
    "rt_movie_id": "e7df9f34-fad6-4972-a225-d8071b6d6dab", 
    "exclude_from_backtest": True,
    },

    "the_housemaid": {
    "title": "The Housemaid",
    "base_rate": 62,  # base_rate=62: 无前作；导演 Paul Feig（Bridesmaids ~90, A Simple Favor ~85），惊悚改编取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHEHOUSEMAID",
    "kalshi_settle_date": "2025-12-22",   
    "final_score_official": 75,   
    "rt_movie_id": "3b5fd007-cfd7-4cc3-8447-f54108145d33", 
    },

    "wake_up_dead_man_a_knives_out_mystery": {
    "title": "Wake Up Dead Man: A Knives Out Mystery",
    "base_rate": 92,  # base_rate=92: Knives Out 系列（~97, Glass Onion ~92），导演 Rian Johnson 直系续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWAKEUPDEADMAN",
    "kalshi_settle_date": "2025-12-01",   
    "final_score_official": 95,   
    "rt_movie_id": "fac916ff-52c7-4164-af63-e8a36bc691b5", 
    },

    "marty_supreme": {
    "title": "Marty Supreme",
    "base_rate": 82,  # base_rate=82: 无前作；导演 Josh Safdie（Uncut Gems ~92, Good Time ~91），A24 剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTMARTYSUPREME",
    "kalshi_settle_date": "2025-12-29",   
    "final_score_official": 95,   
    "rt_movie_id": "b56ad714-d321-3bb9-bb1f-b55504e50dfd", 
    },

    "anaconda": {
    "title": "Anaconda",
    "base_rate": 45,  # base_rate=45: 前作 Anaconda (1997) ~40，重启版；动物恐怖类型
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTANACONDA",
    "kalshi_settle_date": "2025-12-29",   
    "final_score_official": 52,   
    "rt_movie_id": "da8971bf-371d-4bbf-b004-ca65ad8c3fe9", 
    },

    "five_nights_at_freddys_2": {
    "title": "Five Nights At Freddys 2",
    "base_rate": 35,  # base_rate=35: 前作 FNAF (2023) ~33，同 Blumhouse 游戏改编续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTFNAF2",
    "kalshi_settle_date": "2025-12-08",   
    "final_score_official": 12,   
    "rt_movie_id": "65e5f639-a938-41c1-a4ae-ed0284187f74", 
    },

    "ella_mccay": {
    "title": "Ella McCay",
    "base_rate": 72,  # base_rate=72: 无前作；导演 James L. Brooks（As Good as It Gets ~85, Broadcast News ~98, Spanglish ~52），剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTELLAMCCAY",
    "kalshi_settle_date": "2025-12-15",   
    "final_score_official": 22,   
    "rt_movie_id": "a156f25f-4f41-3389-b335-ced5651a3cfb", 
    },

    "now_you_see_me_now_you_dont": {
    "title": "Now You See Me: Now You Don’t",
    "base_rate": 45,  # base_rate=45: 惊天魔盗团系列均分（1 ~50, 2 ~34），续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTNOWYOUSEEME3",
    "kalshi_settle_date": "2025-11-17",   
    "final_score_official": 59,   
    "rt_movie_id": "b15da0eb-808f-4b66-8c1d-336df94cbcc9", 
    },

    "sarahs_oil": {
    "title": "Sarah’s Oil",
    "base_rate": 65,  # base_rate=65: 无信息；历史剧情/家庭片类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTSARAHSOIL",
    "kalshi_settle_date": "2025-11-10",   
    "final_score_official": 80,   
    "rt_movie_id": "23e7189c-ac04-4a1e-ba3b-f73c96a4b8e1", 
    },

    "anniversary": {
        "embargo_date": "2025-10-28",
    "title": "Anniversary",
    "base_rate": 60,  # base_rate=60: 无信息；剧情/惊悚类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTANNIVERSARY",
    "kalshi_settle_date": "2025-11-03",   
    "final_score_official": 68,   
    "rt_movie_id": "cd3732b4-2c34-41af-9997-61965051efeb", 
    },

    "rental_family": {
    "title": "Rental Family",
    "base_rate": 68,  # base_rate=68: 无前作；剧情喜剧类型均分（Searchlight 出品，略调高）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTRENTALFAMILY",
    "kalshi_settle_date": "2025-11-24",   
    "final_score_official": 88,   
    "rt_movie_id": "b17da9f6-43f3-3516-b4e7-d6509858c8b3", 
    },

    "springsteen_deliver_me_from_nowhere": {
    "title": "Springsteen: Deliver Me from Nowhere",
    "base_rate": 70,  # base_rate=70: 无前作；音乐传记片类型均分（导演 Scott Cooper: Crazy Heart ~92, Hostiles ~72）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTSPRINGSTEEN",
    "kalshi_settle_date": "2025-10-27",   
    "final_score_official": 60,   
    "rt_movie_id": "e6a9d95f-fd25-3f38-acce-8692be619173", 
    },

    "the_running_man": {
    "title": "The Running Man",
    "base_rate": 70,  # base_rate=70: 无直系前作参照（重拍）；导演 Edgar Wright（Baby Driver ~92, Last Night in Soho ~74, Hot Fuzz ~91），动作取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHERUNNINGMAN",
    "kalshi_settle_date": "2025-11-17",   
    "final_score_official": 65,   
    "rt_movie_id": "be98ebdc-5255-3e1e-bc11-c98ba3211872", 
    },

    "predator_badlands": {
    "title": "Predator: Badlands",
    "base_rate": 78,  # base_rate=78: 铁血战士系列 + 导演 Dan Trachtenberg（Prey ~94），近作口碑回升，取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTPREDATORBADLANDS",
    "kalshi_settle_date": "2025-11-10",   
    "final_score_official": 85,   
    "rt_movie_id": "a67b0249-887e-45d4-b06c-cd2a018b755e", 
    },

    "regretting_you": {
    "title": "Regretting You",
    "base_rate": 50,  # base_rate=50: 无前作；Colleen Hoover 小说改编爱情剧情（此类改编影评普遍偏低）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTREGRETTINGYOU",
    "kalshi_settle_date": "2025-10-27",   
    "final_score_official": 30,   
    "rt_movie_id": "67aac67e-0ab4-4bd7-926e-38e640a69bd1", 
    },

    "black_phone_2": {
        "embargo_date": "2025-10-15",
    "title": "Black Phone 2",
    "base_rate": 82,  # base_rate=82: 前作 The Black Phone (2021) ~83，同 Scott Derrickson 续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTBLACKPHONE2",
    "kalshi_settle_date": "2025-10-20",   
    "final_score_official": 74,   
    "rt_movie_id": "6361a03b-e8df-3e9f-bdd8-ebcf034f0cd7", 
    },

    "roofman": {
    "title": "Roofman",
    "base_rate": 72,  # base_rate=72: 无前作；导演 Derek Cianfrance（Blue Valentine ~87, A Place Beyond the Pines ~80），犯罪剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTROOFMAN",
    "kalshi_settle_date": "2025-10-13",   
    "final_score_official": 84,   
    "rt_movie_id": "aa6193a9-de60-4193-9f96-e8793fcd8e29", 
    },

    "the_smashing_machine": {
    "title": "The Smashing Machine",
    "base_rate": 78,  # base_rate=78: 无前作；导演 Benny Safdie（Uncut Gems ~92），A24 体育传记取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHESMASHINGMACHINE",
    "kalshi_settle_date": "2025-10-06",   
    "final_score_official": 73,   
    "rt_movie_id": "71111caf-3622-455b-a6b8-6adc5cfef4c0", 
    },

    "tron_ares": {
    "title": "Tron: Ares",
    "base_rate": 55,  # base_rate=55: Tron 系列均分（Legacy ~51），科幻续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTRONARES",
    "kalshi_settle_date": "2025-10-13",   
    "final_score_official": 57,   
    "rt_movie_id": "dcee4e37-65ab-4d3b-80a3-4c673cd0646c", 
    },

    "the_long_walk": {
    "title": "The Long Walk",
    "base_rate": 75,  # base_rate=75: 无前作；斯蒂芬·金改编 + 导演 Francis Lawrence（Hunger Games 系列 ~85-97, Constantine ~46），剧情惊悚取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHELONGWALK",
    "kalshi_settle_date": "2025-09-15",   
    "final_score_official": 90,   
    "rt_movie_id": "531351eb-6173-49d1-902a-7da98c4214d4", 
    },

    "caught_stealing": {
        "embargo_date": "2025-08-24",
    "title": "Caught Stealing",
    "base_rate": 82,  # base_rate=82: 无前作；导演 Darren Aronofsky（Black Swan ~89, The Whale ~64, Requiem ~78），犯罪剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTCAUGHTSTEALING",
    "kalshi_settle_date": "2025-09-01",   
    "final_score_official": 84,   
    "rt_movie_id": "1574f5e9-181c-34d6-a081-d1124f36012e", 
    },

    "one_battle_after_another": {
    "title": "One Battle After Another",
    "base_rate": 88,  # base_rate=88: 无前作；导演 Paul Thomas Anderson（There Will Be Blood ~91, Licorice Pizza ~91, Phantom Thread ~91），近作均分极高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTONEBATTLEAFTERANOTHER",
    "kalshi_settle_date": "2025-09-29",   
    "final_score_official": 96,   
    "rt_movie_id": "32a51ae8-3de5-3f80-9a74-a80dd7bc953b", 
    },

    "downton_abbey_the_grand_finale": {
    "title": "Downton Abbey: The Grand Finale",
    "base_rate": 84,  # base_rate=84: 前两部电影（2019 ~84, A New Era ~85）+ 剧集，直系续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTDOWNTONABBEY",
    "kalshi_settle_date": "2025-09-15",   
    "final_score_official": 91,   
    "rt_movie_id": "3c75d64e-33af-44e1-9324-3b12e4fa10a1", 
    },

    "him": {
    "title": "Him",
    "base_rate": 60,  # base_rate=60: 无前作；Jordan Peele 监制恐怖片（Monkeypaw 出品），恐怖类型取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTHIM",
    "kalshi_settle_date": "2025-09-22",   
    "final_score_official": 29,   
    "rt_movie_id": "15787e2f-4718-483b-9e45-3596ad9dfd5c", 
    },

    "the_conjuring_last_rites": {
    "title": "The Conjuring: Last Rites",
    "base_rate": 75,  # base_rate=75: 招魂宇宙主线均分（Conjuring 1 ~86, 2 ~80, 3 ~56），系列续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTCONJURING",
    "kalshi_settle_date": "2025-09-08",   
    "final_score_official": 56,   
    "rt_movie_id": "17971b95-3589-37b6-a2c3-21f2c2d4eaa7", 
    },

    "honey_dont": {
    "title": "Honey Don’t!",
    "base_rate": 72,  # base_rate=72: 无直系前作；导演 Ethan Coen（Drive-Away Dolls ~66, 科恩兄弟历史高），喜剧取中性偏高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTHONEYDONT",
    "kalshi_settle_date": "2025-08-25",   
    "final_score_official": 45,   
    "rt_movie_id": "a969d4ea-c5ba-424f-9730-5d870ad8c3cf", 
    },

    "the_roses": {
    "title": "The Roses",
    "base_rate": 72,  # base_rate=72: 无直系前作（翻拍 War of the Roses ~84）；导演 Jay Roach（Bombshell ~68, Trumbo ~75），黑色喜剧取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTROSES",
    "kalshi_settle_date": "2025-09-01",   
    "final_score_official": 65,   
    "rt_movie_id": "f0cf2f81-f490-4906-ac97-188c9b9ecfd7", 
    },

    "nobody_2": {
    "title": "Nobody 2",
    "base_rate": 82,  # base_rate=82: 前作 Nobody (2021) ~84，同班底动作续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTNOBODY2",
    "kalshi_settle_date": "2025-08-18",   
    "final_score_official": 76,   
    "rt_movie_id": "9825bc2f-c046-47e0-aca8-8e395adcec9e", 
    },

    "americana": {
    "title": "Americana",
    "base_rate": 65,  # base_rate=65: 无前作；犯罪剧情独立片类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTAMERICANA",
    "kalshi_settle_date": "2025-08-18",   
    "final_score_official": 68,   
    "rt_movie_id": "4926d945-1954-40d4-9457-e23e96c2e89b", 
    "exclude_from_backtest": True,
    },

    "weapons": {
    "title": "Weapons",
    "base_rate": 82,  # base_rate=82: 无前作；导演 Zach Cregger（Barbarian ~92），恐怖类型近作取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWEAPONS",
    "kalshi_settle_date": "2025-08-11",   
    "final_score_official": 95,   
    "rt_movie_id": "e5c17623-fa17-40db-93c6-e34c3db3afca", 
    },

    "the_naked_gun": {
    "title": "The Naked Gun",
    "base_rate": 72,  # base_rate=72: 白头神探系列（原三部曲极高 ~85-96），重启版取中性偏高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTNAKEDGUN",
    "kalshi_settle_date": "2025-08-04",   
    "final_score_official": 90,   
    "rt_movie_id": "e4370cdf-1368-3595-b0bc-a59c63d82fea", 
    },

    "freakier_friday": {
    "title": "Freakier Friday",
    "base_rate": 72,  # base_rate=72: 前作 Freaky Friday (2003) ~88，迪士尼家庭续集，略降
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTFREAKIERFRIDAY",
    "kalshi_settle_date": "2025-08-11",   
    "final_score_official": 73,   
    "rt_movie_id": "e095cc94-a6f3-3a65-9fd0-b591c2a5337e", 
    },

    "i_know_what_you_did_last_summer": {
    "title": "I Know What You Did Last Summer",
    "base_rate": 42,  # base_rate=42: 系列均分（1997 ~43），重启版恐怖续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXLASTSUMMER",
    "kalshi_settle_date": "2025-07-21",   
    "final_score_official": 38,   
    "rt_movie_id": "18f739a9-cfcf-41ca-ac72-ccb11790ab04", 
    },

    "happy_gilmore_2": {
    "title": "Happy Gilmore 2",
    "base_rate": 62,  # base_rate=62: 前作 Happy Gilmore (1996) ~62，Sandler/Netflix 喜剧续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTHAPPYGILMORE2",
    "kalshi_settle_date": "2025-07-28",   
    "final_score_official": 66,   
    "rt_movie_id": "f277c495-5e6c-40fa-b0f9-88e351811268", 
    },

    "elio": {
    "title": "Elio",
    "base_rate": 78,  # base_rate=78: 皮克斯原创动画，皮克斯原创质量带
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTELIO",
    "kalshi_settle_date": "2025-07-23",   
    "final_score_official": 84,   
    "rt_movie_id": "359b8205-52c7-4d8d-86bd-2cb1528bd855", 
    },

    "smurfs": {
        "embargo_date": "2025-07-16",
    "title": "Smurfs",
    "base_rate": 40,  # base_rate=40: 蓝精灵系列历史偏低（前作真人版 ~20-40, 动画版 ~60），家庭动画取中低
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTSMURFS",
    "kalshi_settle_date": "2025-07-21",   
    "final_score_official": 21,   
    "rt_movie_id": "1cdd2ed9-5deb-3a35-9780-e680da13266c", 
    },

    "jurassic_world_rebirth": {
        "embargo_date": "2025-06-30",
    "title": "Jurassic World Rebirth",
    "base_rate": 55,  # base_rate=55: 侏罗纪世界系列均分（近作 ~29-47），大片续集，导演 Gareth Edwards 略调高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTJURASSICWORLDREBIRTH",
    "kalshi_settle_date": "2025-07-07",   
    "final_score_official": 52,   
    "rt_movie_id": "faed754c-1f75-30ac-9d93-5e479892db18", 
    },

    "m3gan_2": {
    "title": "M3GAN 2.0",
    "base_rate": 88,  # base_rate=88: 前作 M3GAN (2023) ~93，同 Blumhouse 续集，略降
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTM3GAN2",
    "kalshi_settle_date": "2025-06-30",   
    "final_score_official": 58,   
    "rt_movie_id": "87258922-27e9-3394-8289-717bacb7abc5", 
    },

    "f1": {
    "title": "F1",
    "base_rate": 82,  # base_rate=82: 无前作；导演 Joseph Kosinski（Top Gun Maverick ~96, Oblivion ~54），体育大片取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTF1",
    "kalshi_settle_date": "2025-06-30",   
    "final_score_official": 83,   
    "rt_movie_id": "e4ccc442-c408-47cb-ad75-bf1dbb45f0c5", 
    },

    "materialists": {
    "title": "Materialists",
    "base_rate": 84,  # base_rate=84: 无前作；导演 Celine Song（Past Lives ~95），A24 爱情剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTMATERIALISTS",
    "kalshi_settle_date": "2025-06-16",   
    "final_score_official": 86,   
    "rt_movie_id": "3ef4e1ed-cc45-3e2b-9c27-2a0e32940c40", 
    },

    "28_years_later": {
    "title": "28 Years Later",
    "base_rate": 85,  # base_rate=85: 28 系列（28 Days Later ~87, 28 Weeks Later ~72），导演 Danny Boyle 回归续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT28YEARSLATER",
    "kalshi_settle_date": "2025-06-23",   
    "final_score_official": 89,   
    "rt_movie_id": "51fd2488-398d-4c57-9991-708e28151acf", 
    },

    "how_to_train_your_dragon": {
        "embargo_date": "2025-06-11",
    "title": "How to Train Your Dragon",
    "base_rate": 77,  # base_rate=77: 前作动画三部曲极高（~98, ~92, ~90），迪士尼那批真人翻拍(狮子王、小美人鱼)普遍比动画原作降不少
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTHOWTOTRAINYOURDRAGON",
    "kalshi_settle_date": "2025-06-16",   
    "final_score_official": 77,   
    "rt_movie_id": "2e7f28de-a4d2-4258-a4f0-51d960dab966", 
    },

    "from_the_world_of_john_wick_ballerina": {
    "title": "From the World of John Wick: Ballerina",
    "base_rate": 82,  # base_rate=82: John Wick 宇宙均分（系列 ~86-94），衍生动作片
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTJWBALLERINA",
    "kalshi_settle_date": "2025-06-09",   
    "final_score_official": 75,   
    "rt_movie_id": "21465384-f9d9-4977-97fa-40dc33805cca", 
    },

    "karate_kid_legends": {
        "embargo_date": "2025-05-28",
    "title": "Karate Kid: Legends",
    "base_rate": 62,  # base_rate=62: 系列均分（2010 版 ~67, Cobra Kai 剧集高），动作续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTKARATEKIDLEGENDS",
    "kalshi_settle_date": "2025-06-02",   
    "final_score_official": 59,   
    "rt_movie_id": "e373558a-5a30-3c9f-b90a-94dd5f4cbd46", 
    },

    "fight_or_flight": {
        "embargo_date": "2025-05-09",
    "title": "Fight or Flight",
    "base_rate": 60,  # base_rate=60: 无前作；动作喜剧类型历史均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTFIGHTORFLIGHT",
    "kalshi_settle_date": "2025-03-12",   
    "final_score_official": 77,   
    "rt_movie_id": "5aacdaf0-089b-3bfb-b746-09c9571aa370", 
    },

    "lilo_and_stitch": {
    "title": "Lilo & Stitch",
    "base_rate": 62,  # base_rate=62: 迪士尼真人翻拍近期水位（原动画 ~86，翻拍普遍降至 60-70）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTLILOANDSTITCH",
    "kalshi_settle_date": "2025-05-26",   
    "final_score_official": 68,   
    "rt_movie_id": "67103af9-9396-4300-a143-b8ef4a354c9a", 
    },

    "final_destination_bloodlines": {
    "title": "Final Destination: Bloodlines",
    "base_rate": 62,  # base_rate=62: 死神来了系列均分（1 ~72, 后续 ~40-60），恐怖续集，略调高（口碑回暖预期）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTFDBLOODLINES",
    "kalshi_settle_date": "2025-05-19",   
    "final_score_official": 93,   
    "rt_movie_id": "f2856add-d345-3de6-93dd-4aefaec9b3d2", 
    },

    "mission_impossible_the_final_reckoning": {
    "title": "Mission: Impossible – The Final Reckoning",
    "base_rate": 88,  # base_rate=88: 碟中谍近作均分（Fallout ~97, Dead Reckoning ~96），系列续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXMISSIONIMPOSSIBLE",
    "kalshi_settle_date": "2025-05-26",   
    "final_score_official": 80,   
    "rt_movie_id": "ea92223a-365b-30c7-99d7-06e90000e408", 
    },

    "thunderbolts": {
    "title": "Thunderbolts",
    "base_rate": 68,  # base_rate=68: 近期漫威 MCU 阶段水位（品控波动），超英团队片取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHUNDERBOLTS",
    "kalshi_settle_date": "2025-05-05",   
    "final_score_official": 88,   
    "rt_movie_id": "38285217-4a57-4ab1-a4f1-fc958c5937c1", 
    },

    "the_accountant_2": {
    "title": "The Accountant 2",
    "base_rate": 65,  # base_rate=65: 前作 The Accountant (2016) ~52，同 Gavin O'Connor/Affleck 续集，略调高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTACCOUNTANT2",
    "kalshi_settle_date": "2025-04-28",   
    "final_score_official": 78,   
    "rt_movie_id": "58256c6a-1d39-3328-92ab-48d21879f36f", 
    },

    "clown_in_a_cornfield": {
    "title": "Clown in a Cornfield",
    "base_rate": 65,  # base_rate=65: 无前作；恐怖小说改编，恐怖类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTCLOWNINACORNFIELD",
    "kalshi_settle_date": "2025-05-12",   
    "final_score_official": 74,   
    "rt_movie_id": "bac73621-3388-31a5-95e7-7ac533f51879", 
    },

    "sinners": {
    "title": "Sinners",
    "base_rate": 88,  # base_rate=88: 无前作；导演 Ryan Coogler（Black Panther ~96, Creed ~95, Fruitvale ~94），近作均分极高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTSINNERS",
    "kalshi_settle_date": "2025-04-21",   
    "final_score_official": 98,   
    "rt_movie_id": "c38675e0-a0a8-4cbb-9bbc-1a5754b6c08e", 
    },

    "warfare": {
    "title": "Warfare",
    "base_rate": 82,  # base_rate=82: 无前作；导演 Alex Garland（Civil War ~83, Ex Machina ~92, Annihilation ~88），战争片取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWARFARE",
    "kalshi_settle_date": "2025-04-14",   
    "final_score_official": 94,   
    "rt_movie_id": "3ef6ed4e-b35e-4153-95fe-841b08286861", 
    },

    "the_amateur": {
        "embargo_date": "2026-04-08",
    "title": "The Amateur",
    "base_rate": 68,  # base_rate=68: 无直系前作（翻拍 1981）；导演 James Hawes（One Life ~85），惊悚动作取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHEAMATEUR",
    "kalshi_settle_date": "2025-04-14",   
    "final_score_official": 61,   
    "rt_movie_id": "247bd9a7-b198-479b-a40e-58485b119be9", 
    },

    "the_woman_in_the_yard": {
    "title": "The Woman in the Yard",
    "base_rate": 55,  # base_rate=55: 无前作；导演 Jaume Collet-Serra（近作波动大），Blumhouse 恐怖取中性偏低
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHEWOMANINTHEYARD",
    "kalshi_settle_date": "2025-03-31",   
    "final_score_official": 43,   
    "rt_movie_id": "99c358aa-e34f-3e58-afa5-abc8881cf911", 
    },

    "last_breath": {
    "title": "Last Breath",
    "base_rate": 78,  # base_rate=78: 无前作；改编自同名纪录片（~98），剧情惊悚取中高保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTLASTBREATH",
    "kalshi_settle_date": "2025-03-03",   
    "final_score_official": 76,   
    "rt_movie_id": "fa80bbde-0fa7-3bb6-b721-061d792dbfc0", 
    },

    "unbreakable_boy": {
    "title": "Unbreakable Boy",
    "base_rate": 55,  # base_rate=55: 无前作；信仰/家庭剧情片类型均分（此类片影评普遍偏低）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTUNBREAKABLEBOY",
    "kalshi_settle_date": "2025-02-24",   
    "final_score_official": 45,   
    "rt_movie_id": "a0d43227-0532-326e-9f4c-f3f4f07901c8", 
    },

    "heart_eyes": {
    "title": "Heart Eyes",
    "base_rate": 72,  # base_rate=72: 无前作；恐怖喜剧类型历史均分（Spooky/rom-com hybrid 近期口碑不错）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTHEARTEYES",
    "kalshi_settle_date": "2025-02-10",   
    "final_score_official": 77,   
    "rt_movie_id": "7de8e94c-f8c1-4666-8346-3f33b7f939dd", 
    },

    "dog_man": {
    "title": "Dog Man",
    "base_rate": 72,  # base_rate=72: 无直系前作；DreamWorks/Captain Underpants 宇宙（~87），家庭动画取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTDOGMAN",
    "kalshi_settle_date": "2025-02-03",   
    "final_score_official": 78,   
    "rt_movie_id": "47727a4b-7892-35aa-bd6c-6335192a913d", 
    },

    "flight_risk": {
    "title": "Flight Risk",
    "base_rate": 42,  # base_rate=42: 无前作；导演 Mel Gibson（Hacksaw Ridge ~84, 但惊悚片方向），动作惊悚取中低
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTFLIGHTRISK",
    "kalshi_settle_date": "2025-01-27",   
    "final_score_official": 26,   
    "rt_movie_id": "20979927-2f4d-4818-8363-64ef90f809d0", 
    },

    "the_damned": {
    "title": "The Damned",
    "base_rate": 68,  # base_rate=68: 无前作；民俗恐怖/剧情独立片类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTTHEDAMNED",
    "kalshi_settle_date": "2025-01-06",   
    "final_score_official": 85,   
    "rt_movie_id": "436edeef-36d3-3f58-b1b5-baf0a9d3c630", 
    "exclude_from_backtest": True,
    },

    "wolf_man": {
    "title": "Wolf Man",
    "base_rate": 55,  # base_rate=55: 无直系前作；导演 Leigh Whannell（Invisible Man ~92, Upgrade ~88），恐怖取中性（怪物翻拍不确定）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWOLFMAN",
    "kalshi_settle_date": "2025-01-20",   
    "final_score_official": 52,   
    "rt_movie_id": "0ea92e83-d367-424e-bb05-d5d167616831", 
    },

    "den_of_thieves_2": {
        "embargo_date": "2025-01-09",
    "title": "Den of Thieves 2: Pantera",
    "base_rate": 62,  # base_rate=62: 前作 Den of Thieves (2018) ~41，同 Gerard Butler 犯罪续集，略调高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTDENOFTHIEVES",
    "kalshi_settle_date": "2025-01-13",   
    "final_score_official": 57,   
    "rt_movie_id": "473722bf-6869-3ce3-b7c8-796a410eeb95", 
    },

    "sonic_the_hedgehog_3": {
    "title": "Sonic The Hedgehog 3",
    "base_rate": 75,  # base_rate=75: 索尼克系列均分（1 ~63, 2 ~69），游戏改编续集，口碑上升趋势
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTSONIC3",
    "kalshi_settle_date": "2024-12-23",   
    "final_score_official": 87,   
    "rt_movie_id": "3b1abf49-2e73-46c1-91c5-4ba78690ca2a", 
    },

    "kraven_the_hunter": {
    "title": "Kraven the Hunter",
    "base_rate": 40,  # base_rate=40: 索尼漫威宇宙（SSU）历史偏低（Morbius ~15, Madame Web ~11, Venom ~30-58），超英取中低
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTKRAVEN",
    "kalshi_settle_date": "2024-12-16",   
    "final_score_official": 15,   
    "rt_movie_id": "f4872248-b460-3840-9d66-4d3578bd5f3d", 
    },

    "a_complete_unknown": {
    "title": "A Complete Unknown",
    "base_rate": 82,  # base_rate=82: 无前作；导演 James Mangold（Ford v Ferrari ~92, Walk the Line ~83, Logan ~94），音乐传记取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTACOMPLETEUNKNOWN",
    "kalshi_settle_date": "2024-12-30",   
    "final_score_official": 77,   
    "rt_movie_id": "54d59ec6-af57-4c3b-8880-c13bcbad9f26", 
    },

    "lord_of_the_rings_war_of_the_rohirrim": {
        "embargo_date": "2024-12-09",
    "title": "Lord of the Rings: War of the Rohirrim",
    "base_rate": 75,  # base_rate=75: 中土宇宙动画衍生；LOTR 电影历史极高但动画外传取中高保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWAROFTHEROHIRRIM",
    "kalshi_settle_date": "2024-12-16",   
    "final_score_official": 51,   
    "rt_movie_id": "af3a4d13-b37e-41c2-938b-532eace1ff7a", 
    },

    "nightbitch": {
    "title": "Nightbitch",
    "base_rate": 68,  # base_rate=68: 无前作；导演 Marielle Heller（Can You Ever Forgive Me ~98, A Beautiful Day ~80），剧情取中高但题材不确定，保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTNIGHTBITCH",
    "kalshi_settle_date": "2024-12-09",   
    "final_score_official": 59,   
    "rt_movie_id": "c82ec11d-c101-3388-9943-10b6db21244b", 
    },

    "red_one": {
    "title": "Red One",
    "base_rate": 58,  # base_rate=58: 无前作；节日动作喜剧类型历史均分（大成本合家欢近期口碑偏低）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTREDONE",
    "kalshi_settle_date": "2024-11-18",   
    "final_score_official": 33,   
    "rt_movie_id": "b4675d53-5243-33d9-81af-e450f6f98440", 
    },

    "the_best_christmas_pageant_ever": {
        "embargo_date": "2024-11-06",
    "title": "The Best Christmas Pageant Ever",
    "base_rate": 72,  # base_rate=72: 无前作；家庭/信仰节日剧情类型均分（Kingdom Story 出品，略调高）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTCHRISTMASPAGEANT",
    "kalshi_settle_date": "2024-11-11",   
    "final_score_official": 89,   
    "rt_movie_id": "5a380052-96db-39ca-b7ae-dad094b4122e", 
    },

    "the_apprentice": {
    "title": "The Apprentice",
    "base_rate": 78,  # base_rate=78: 无前作；导演 Ali Abbasi（Holy Spider ~96, Border ~96），政治传记剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTAPPRENTICE",
    "kalshi_settle_date": "2024-10-14",   
    "final_score_official": 78,   
    "rt_movie_id": "4477d0c1-e5ae-316f-9d08-14af792a78b9", 
    "exclude_from_backtest": True,
    },

    "venom_the_last_dance": {
    "title": "Venom: The Last Dance",
    "base_rate": 45,  # base_rate=45: 毒液系列均分（1 ~30, 2 ~57），SSU 续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTVENOM3",
    "kalshi_settle_date": "2024-10-28",   
    "final_score_official": 37,   
    "rt_movie_id": "0f101f8c-ec09-39c4-9be0-2f9cc464d332", 
    },

    "the_wild_robot": {
        "embargo_date": "2024-09-08",
    "title": "The Wild Robot",
    "base_rate": 92,  # base_rate=92: 无前作；DreamWorks 原创动画（近作 Puss in Boots 2 ~95），高口碑动画带
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTWILDROBOT",
    "kalshi_settle_date": "2024-09-30",   
    "final_score_official": 98,   
    "rt_movie_id": "dd36be73-6c5e-3b4b-94e2-4b62260e2808", 
    },

    "smile_2": {
    "title": "Smile 2",
    "base_rate": 82,  # base_rate=82: 前作 Smile (2022) ~79，同班底恐怖续集，略调高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTSMILE2",
    "kalshi_settle_date": "2024-10-21",   
    "final_score_official": 84,   
    "rt_movie_id": "e7eb406d-4ebf-46cb-98a9-e0b2a5e3d784", 
    },

    "terrifier_3": {
        "embargo_date": "2024-09-19",
    "title": "Terrifier 3",
    "base_rate": 78,  # base_rate=78: 系列均分（Terrifier 2 ~85），Cult 恐怖续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTTERRIFIER3",
    "kalshi_settle_date": "2024-10-14",   
    "final_score_official": 76,   
    "rt_movie_id": "d28fe459-58cd-38c4-b2b7-61ed8ec21132", 
    },

    "speak_no_evil": {
    "title": "Speak No Evil",
    "base_rate": 72,  # base_rate=72: 翻拍自 2022 丹麦版（~85），Blumhouse 惊悚，取中性偏高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTSPEAKNOEVIL",
    "kalshi_settle_date": "2024-09-16",   
    "final_score_official": 85,   
    "rt_movie_id": "1f8b4ca3-de3f-4af8-82b3-8c023dd98fa3", 
    },

    "beetlejuice_beetlejuice": {
    "title": "Beetlejuice Beetlejuice",
    "base_rate": 76,  # base_rate=76: 前作 Beetlejuice (1988) ~85，Tim Burton 直系续集，略降
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTBEETLEJUICE",
    "kalshi_settle_date": "2024-09-09",   
    "final_score_official": 76,   
    "rt_movie_id": "e0dbe905-8617-3930-9128-50868ea9d29b", 
    },

    "reagan": {
        "embargo_date": "2024-08-30",
    "title": "Reagan",
    "base_rate": 40,  # base_rate=40: 无前作；政治传记片（此类党派题材影评普遍两极偏低）
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTREAGAN",
    "kalshi_settle_date": "2024-09-02",   
    "final_score_official": 18,   
    "rt_movie_id": "6fea83dd-e4ad-3702-a5ec-085235a63497", 
    },

    "trap": {
    "title": "Trap",
    "base_rate": 62,  # base_rate=62: 无直系前作；导演 M. Night Shyamalan 近作波动大（Old ~50, Knock at the Cabin ~68），惊悚取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTTRAP",
    "kalshi_settle_date": "2024-08-05",   
    "final_score_official": 50,   
    "rt_movie_id": "16d55cfd-4b3d-3e0c-b69a-6b55ac7c9fd2", 
    },

    "twisters": {
    "title": "Twisters",
    "base_rate": 72,  # base_rate=72: 前作 Twister (1996) ~65，导演 Lee Isaac Chung（Minari ~98），灾难续集取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTTWISTERS",
    "kalshi_settle_date": "2024-07-22",   
    "final_score_official": 77,   
    "rt_movie_id": "ae418d31-ae6e-4924-90bd-ce9e59dba91a", 
    },

    "transformers_one": {
    "title": "Transformers One",
    "base_rate": 65,  # base_rate=65: 变形金刚系列均分（真人片 ~15-57），但动画前传+好评预期，大幅调高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTTRANSFORMERSONE",
    "kalshi_settle_date": "2024-09-23",   
    "final_score_official": 88,   
    "rt_movie_id": "3e8fc409-302f-45db-939f-1662b0d032bc", 
    },

    "fly_me_to_the_moon": {
        "embargo_date": "2024-07-09",
    "title": "Fly Me to the Moon",
    "base_rate": 70,  # base_rate=70: 无前作；导演 Greg Berlanti（Love, Simon ~92），爱情喜剧剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTFLYMETOTHEMOON",
    "kalshi_settle_date": "2024-07-15",   
    "final_score_official": 67,   
    "rt_movie_id": "f59ca50b-acc6-4255-a4a2-c81b396367ff", 
    },

    "despicable_me_4": {
        "embargo_date": "2024-06-19",
    "title": "Despicable Me 4",
    "base_rate": 68,  # base_rate=68: 神偷奶爸系列均分（1 ~81, 2 ~59, 3 ~59），照明动画续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTDESPICABLEME4",
    "kalshi_settle_date": "2024-07-08",   
    "final_score_official": 53,   
    "rt_movie_id": "8ad497d8-01d4-4183-a8a2-89bbbd413936", 
    },

    "a_quiet_place_day_one": {
    "title": "A Quiet Place: Day One",
    "base_rate": 88,  # base_rate=88: 寂静之地系列（1 ~96, 2 ~91），衍生前传，取系列水位保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTQUIETPLACEDAYONE",
    "kalshi_settle_date": "2024-07-01",   
    "final_score_official": 85,   
    "rt_movie_id": "735950fc-8fd6-315e-887b-84c471183f1a", 
    },

    "inside_out_2": {
    "title": "Inside Out 2",
    "base_rate": 90,  # base_rate=90: 头脑特工队 1 (~98)，皮克斯续集，取保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTINSIDEOUT2",
    "kalshi_settle_date": "2024-06-17",   
    "final_score_official": 91,   
    "rt_movie_id": "44b2d9e4-973e-3047-b118-1fc706f0482d", 
    },

    "the_watchers": {
    "title": "The Watchers",
    "base_rate": 55,  # base_rate=55: 无前作；导演 Ishana Night Shyamalan 处女作，恐怖类型均分兜底
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTWATCHERS",
    "kalshi_settle_date": "2024-06-10",   
    "final_score_official": 29,   
    "rt_movie_id": "e793d83d-d401-32e3-a790-c2df7d2ada43", 
    },

    "the_fall_guy": {
    "title": "The Fall Guy",
    "base_rate": 78,  # base_rate=78: 无前作；导演 David Leitch（Bullet Train ~54, Atomic Blonde ~78, Deadpool 2 ~85），动作喜剧取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTTHEFALLGUY",
    "kalshi_settle_date": "2024-05-06",   
    "final_score_official": 83,   
    "rt_movie_id": "a812f454-c36d-46ba-85fd-93684f55bb7b", 
    },

    "kingdom_of_the_planet_of_the_apes": {
    "title": "Kingdom of the Planet of the Apes",
    "base_rate": 82,  # base_rate=82: 猩球崛起系列均分（近三部 ~82-94），系列续集
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTAPES",
    "kalshi_settle_date": "2024-05-13",   
    "final_score_official": 81,   
    "rt_movie_id": "4caf2155-40f7-482d-95a6-2f6642645bb5", 
    },

    "civil_war": {
    "title": "Civil War",
    "base_rate": 85,  # base_rate=85: 无前作；导演 Alex Garland（Ex Machina ~92, Annihilation ~88, Men ~68），A24 剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTCIVIL",
    "kalshi_settle_date": "2024-04-15",   
    "final_score_official": 83,   
    "rt_movie_id": "b9538a0a-8e95-4da3-b98c-16e14831d546", 
    },

    "challengers": {
    "title": "Challengers",
    "base_rate": 85,  # base_rate=85: 无前作；导演 Luca Guadagnino（Call Me by Your Name ~94, Bones and All ~82, Suspiria ~65），剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTCHALLENGERS",
    "kalshi_settle_date": "2024-04-29",   
    "final_score_official": 88,   
    "rt_movie_id": "8aa567ab-7079-45b2-af27-fff5c410ae82", 
    },

    "kinds_of_kindness": {
    "title": "Kinds of Kindness",
    "base_rate": 82,  # base_rate=82: 无直系前作；导演 Yorgos Lanthimos（Poor Things ~92, The Favourite ~93, The Lobster ~87），剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTKINDS",
    "kalshi_settle_date": "2024-06-24",   
    "final_score_official": 74,   
    "rt_movie_id": "112cd1ed-c0ba-32fa-a196-7628d4cb3a44", 
    },

    "alien_romulus": {
    "title": "Alien: Romulus",
    "base_rate": 72,  # base_rate=72: 异形系列均分（波动大 ~63-98），导演 Fede Álvarez（Evil Dead ~63, Don't Breathe ~88），取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTALIENROMULUS",
    "kalshi_settle_date": "2024-08-19",   
    "final_score_official": 82,   
    "rt_movie_id": "1a613dbb-03df-31e0-9ded-5b98ff121b19", 
    },

    "megalopolis": {
    "title": "Megalopolis",
    "base_rate": 60,  # base_rate=60: 无前作；导演 Coppola（近作波动极大，教父级历史但近几十年不稳），实验大片取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTMEGALOPOLIS",
    "kalshi_settle_date": "2024-09-30",   
    "final_score_official": 49,   
    "rt_movie_id": "d2769b11-3c70-4578-b16d-396ee462aa4e", 
    "exclude_from_backtest": True,
    },

    "furiosa": {
    "title": "Furiosa",
    "base_rate": 88,  # base_rate=88: 前作 Mad Max: Fury Road (2015) ~97，同 George Miller 前传，取保守
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTFURIOSA",
    "kalshi_settle_date": "2024-05-27",   
    "final_score_official": 90,   
    "rt_movie_id": "23c83c9d-be80-3b75-b74e-8a84ef1a24ae", 
    },

    "blitz": {
    "title": "Blitz",
    "base_rate": 78,  # base_rate=78: 无前作；导演 Steve McQueen（12 Years a Slave ~95, Small Axe 高分），战争剧情取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTBLITZ",
    "kalshi_settle_date": "2024-12-31",   
    "final_score_official": 77,   
    "rt_movie_id": "9be3aa82-eca1-3cca-b566-82115894e8d4", 
    },

    "godzilla_x_kong_the_new_empire": {
        "embargo_date": "2024-03-28",
    "title": "Godzilla X Kong: The New Empire",
    "base_rate": 55,  # base_rate=55: 怪兽宇宙均分（GvK ~76, Godzilla 2014 ~76, KotM ~42），大片续集取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTGODZILLAXKONG",
    "kalshi_settle_date": "2024-04-01",   
    "final_score_official": 55,   
    "rt_movie_id": "9a140a0e-f653-3714-a7cb-6b0a9614d020", 
    },

    "the_first_omen": {
    "title": "The First Omen",
    "base_rate": 60,  # base_rate=60: 凶兆系列（原作 ~86），前传恐怖片取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTFIRSTOMEN",
    "kalshi_settle_date": "2024-04-08",   
    "final_score_official": 79,   
    "rt_movie_id": "1c62ddc4-1e78-38f3-b731-7d6e7d2de4df", 
    },

    "ghostbusters_frozen_empire": {
    "title": "Ghostbusters: Frozen Empire",
    "base_rate": 55,  # base_rate=55: 捉鬼敢死队系列均分（Afterlife ~63, 2016 ~74），续集取中性
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTGHOSTBUSTERFE",
    "kalshi_settle_date": "2024-03-25",   
    "final_score_official": 42,   
    "rt_movie_id": "f0bbe54c-35ce-342f-847d-5228c0360b9b", 
    },

    "joker_folie_a_deux": {
    "title": "Joker: Folie à Deux",
    "base_rate": 68,  # base_rate=68: 前作 Joker (2019) ~68，直系续集（同 Todd Phillips/Phoenix），取前作值
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTJOKER2",
    "kalshi_settle_date": "2024-10-07",   
    "final_score_official": 33,   
    "rt_movie_id": "24287464-bfdc-362a-b386-aa62895c2a1b", 
    },

    "gladiator_2": {
    "title": "Gladiator 2",
    "base_rate": 78,  # base_rate=78: 前作 Gladiator (2000) ~80，导演 Ridley Scott 直系续集，略降
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTGLADIATOR2",
    "kalshi_settle_date": "2024-11-25",   
    "final_score_official": 72,   
    "rt_movie_id": "aeadc0b3-8222-39a9-a3f0-47b28afb5154", 
    },

    "deadpool_and_wolverine": {
    "title": "Deadpool & Wolverine",
    "base_rate": 78,  # base_rate=78: 死侍系列均分（1 ~85, 2 ~84），MCU 续集取中高
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "RTDEADPOOL3",
    "kalshi_settle_date": "2024-07-29",   
    "final_score_official": 79,   
    "rt_movie_id": "1f72f2e7-28cf-35bf-839e-577fd3f41ea3", 
    },



    # ===========================================================
    # =================历史电影栏(Kalshi未开盘的)==================
    # ===========================================================


    
    # 要加电影：复制上面整个 block，改 key 名和里面的值，
    # 并给它自己的 "ladder"（可以复制 DEFAULT_LADDER 当起点）。
}