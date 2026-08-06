"""
Kalshi 平台适配器。包装现有的 kalshi_client 逻辑到统一接口。
结算规则：严格大于（above X = 最终分 > X，即 ≥ X+1）。
"""
from __future__ import annotations

from src.model.bayesian import ModelResult
from src.strategy.decide import Rung
from src.collectors.platforms.base import Platform
from src.collectors import kalshi_client as kc


class KalshiPlatform(Platform):
    name = "kalshi"

    def get_rungs(self, movie_cfg: dict) -> list[Rung]:
        event = movie_cfg.get("kalshi_event")
        if not event:
            return []
        return kc.get_ladder_live(event)   # 已返回 Rung 列表（美分）

    def yes_prob(self, result: ModelResult, floor: float) -> float:
        # Kalshi 严格大于：above X 需要最终分 ≥ X+1
        return result.prob_at_least(floor + 1)

    def fetch_depth(self, rung: Rung, movie_cfg: dict) -> dict:
        """返回统一格式 {yes_asks, no_asks}（美分）。
        Kalshi 只返回 bids，买YES/买NO 从对面 bids 换算：
          买YES = 吃 no_bids（yes_ask@X = no_bid@(100-X)）
          买NO  = 吃 yes_bids（no_ask@Y = yes_bid@(100-Y)）"""
        event = movie_cfg.get("kalshi_event", "")
        ticker = rung.ticker if getattr(rung, "ticker", None) else f"{event}-{int(rung.t)}"
        ob = kc.fetch_market_orderbook(ticker)
        yes_asks = [[100 - p, s] for p, s in ob.get("no_bids", [])]
        no_asks = [[100 - p, s] for p, s in ob.get("yes_bids", [])]
        return {"yes_asks": yes_asks, "no_asks": no_asks}