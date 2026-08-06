"""
Polymarket 平台适配器。
结算规则：大于等于（at least X = 最终分 ≥ X）。
数据源：Gamma API（event/market 元数据）+ CLOB API（orderbook）。读数据不需认证。

Polymarket 特点：
- event slug → markets（各分档），每个 market 有 YES/NO 两个 token
- 价格是 0-1 小数字符串，需 ×100 转美分
- orderbook 返回 bids+asks，但顺序不固定，需自己排序
- clobTokenIds / outcomes 是 stringified JSON，需 json.loads
"""
from __future__ import annotations

import json

import requests

from src.model.bayesian import ModelResult
from src.strategy.decide import Rung
from src.collectors.platforms.base import Platform

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


class PolymarketPlatform(Platform):
    name = "polymarket"

    def get_rungs(self, movie_cfg: dict) -> list[Rung]:
        slug = movie_cfg.get("polymarket_event_slug")
        if not slug:
            return []
        resp = requests.get(f"{GAMMA}/events/slug/{slug}", timeout=15)
        resp.raise_for_status()
        event = resp.json()

        rungs = []
        for m in event.get("markets", []):
            label = m.get("groupItemTitle", "")
            try:
                floor = float(str(label).replace("+", "").strip())
            except (ValueError, TypeError):
                continue
            tokens = self._loads(m.get("clobTokenIds", "[]"))
            yes_token = tokens[0] if tokens else None
            no_token = tokens[1] if len(tokens) > 1 else None

            # YES best 价（best_ask=买YES价，best_bid=卖YES价）
            yes_ask, yes_bid = self._best_yes(yes_token)
            if yes_ask is None:
                continue
            # NO best 价：对 NO token 用同样逻辑，best_ask=买NO价
            no_ask, no_bid = self._best_yes(no_token)
            if no_ask is None:
                no_ask = 100 - yes_bid if yes_bid is not None else 100 - yes_ask

            r = Rung(t=floor, yes_price=yes_ask, no_price=no_ask)
            # 把 token/bid 挂到 Rung 上，fetch_depth 时用
            r.yes_token = yes_token       # 动态属性
            r.no_token = no_token
            r.yes_bid = yes_bid
            rungs.append(r)
        rungs.sort(key=lambda x: x.t)
        return rungs

    def yes_prob(self, result: ModelResult, floor: float) -> float:
        # Polymarket 大于等于：at least X 需要最终分 ≥ X
        return result.prob_at_least(floor)

    def fetch_depth(self, rung: Rung, movie_cfg: dict) -> dict:
        """返回统一格式 {yes_asks, no_asks}（美分，升序）。
        Polymarket 的 YES/NO 是两个独立 token，各有独立 orderbook：
          买YES = 吃 YES token 的 asks
          买NO  = 吃 NO token 的 asks（独立盘口，不从YES换算！）"""
        _, yes_asks = self._book(getattr(rung, "yes_token", None))
        _, no_asks = self._book(getattr(rung, "no_token", None))
        return {"yes_asks": yes_asks, "no_asks": no_asks}

    # ---------- 内部工具 ----------
    @staticmethod
    def _loads(x):
        if isinstance(x, str):
            try:
                return json.loads(x)
            except (json.JSONDecodeError, TypeError):
                return []
        return x or []

    def _book(self, token_id):
        """拉 orderbook，返回 (bids, asks) 美分，自己排序（照搬验证过的临时脚本逻辑）。
        bids 降序（best买价最高在前），asks 升序（best卖价最低在前）。"""
        if not token_id:
            return [], []
        resp = requests.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=15)
        resp.raise_for_status()
        ob = resp.json()
        bids = [[round(float(b["price"]) * 100, 2), float(b["size"])] for b in ob.get("bids", [])]
        asks = [[round(float(a["price"]) * 100, 2), float(a["size"])] for a in ob.get("asks", [])]
        bids.sort(key=lambda x: -x[0])
        asks.sort(key=lambda x: x[0])
        return bids, asks

    def _best_yes(self, token_id):
        """返回 (best_ask, best_bid) 美分。best_ask=买YES价(卖单最低)，best_bid=卖YES价(买单最高)。"""
        bids, asks = self._book(token_id)
        # 照搬临时脚本：best_bid=买单最高价，best_ask=卖单最低价
        best_bid = max((b[0] for b in bids), default=None)
        best_ask = min((a[0] for a in asks), default=None)
        return best_ask, best_bid