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
    # =================历史电影栏(Kalshi开过盘的)==================
    # ===========================================================
    "zootopia_2": {
    "title": "Zootopia 2",
    "base_rate": 90,       # TODO 待定，随便填，抓数据用不到
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTZOOTOPIA2",
    "kalshi_settle_date": "2025-12-01",   # 这个要准（网站查的）
    "final_score_official": 91,   # Kalshi 结算时官方认定的最终 RT 分数（网站查，手动记）
    "rt_movie_id": "47d189ea-dcbd-3992-8cd0-86ff439aa52e", # 这个要准（F12查）
    },

    "avatar_fire_and_ash": {
    "title": "Avatar: Fire And Ash",
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-PRO",
    "kalshi_settle_date": "2025-03-23",   
    "final_score_official": 95,   
    "rt_movie_id": "5c4afb29-9a25-4fac-9a1c-b6a4528b7935", 
    },

    "mufasa": {
    "title": "Mufasa",
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWICKEDFORGOOD",
    "kalshi_settle_date": "2025-11-24",   
    "final_score_official": 70,   
    "rt_movie_id": "37521ff5-0423-314e-812d-7d89d8118496", 
    },

    "the_monkey": {
    "title": "The Monkey",
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-SUP",
    "kalshi_settle_date": "2026-04-06",   
    "final_score_official": 42,   
    "rt_movie_id": "fb281f3f-c572-37fb-ab30-3b0ee07d8454", 
    },

    "wicked": {
    "title": "Wicked",
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTWICKED",
    "kalshi_settle_date": "2024-11-25",   
    "final_score_official": 90,   
    "rt_movie_id": "0fb0ec41-5919-34d5-8731-0c6254471412", 
    },

    "novocaine": {
    "title": "Novocaine",
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTNOSFERATU",
    "kalshi_settle_date": "2024-12-30",   
    "final_score_official": 86,   
    "rt_movie_id": "2112ebcf-e450-360a-9c19-9d2fbdb681e4", 
    },

    "marty_supreme": {
    "title": "Marty Supreme",
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTMARTYSUPREME",
    "kalshi_settle_date": "2024-12-29",   
    "final_score_official": 95,   
    "rt_movie_id": "b56ad714-d321-3bb9-bb1f-b55504e50dfd", 
    },

    "28_years_later_the_bone_temple": {
    "title": "28 Years Later: The Bone Temple",
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT28YEARSLATERTBT",
    "kalshi_settle_date": "2026-01-19",   
    "final_score_official": 93,   
    "rt_movie_id": "8261c2a0-972c-4830-91ce-e625d1dba0dd", 
    },

    "the_drama": {
    "title": "The Drama",
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-REA",
    "kalshi_settle_date": "2026-03-23",   
    "final_score_official": 75,   
    "rt_movie_id": "ba0ab3d6-fa0d-41fb-963a-0ee5ee5cf378", 
    },

    "forbidden_fruits": {
    "title": "Forbidden Fruits",
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRT-WHI",
    "kalshi_settle_date": "2026-02-09",   
    "final_score_official": 61,   
    "rt_movie_id": "6aecc3ba-e804-4de6-b79f-4581bbc1eec4", 
    },

    "melania": {
    "title": "Melania",
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
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
    "base_rate": 90,       # TODO 待定
    "prior_strength": 10,  # TODO 待定
    "drift": 2.0,          # TODO 待校准
    "n_final": 226,        # TODO 待定
    "kalshi_event": "KXRTPRIMATE",
    "kalshi_settle_date": "2026-01-12",   
    "final_score_official": 77,   
    "rt_movie_id": "e7df9f34-fad6-4972-a225-d8071b6d6dab", 
    },


    # ===========================================================
    # =================历史电影栏(Kalshi未开盘的)==================
    # ===========================================================


    
    # 要加电影：复制上面整个 block，改 key 名和里面的值，
    # 并给它自己的 "ladder"（可以复制 DEFAULT_LADDER 当起点）。
}