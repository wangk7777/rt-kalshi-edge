# base.py
class Platform:
    name: str
    def get_rungs(self, movie_cfg) -> list:
        """返回门槛列表，每个含 floor, yes_ask, yes_bid, no_ask, ticker/token"""
    def yes_prob(self, model_result, floor) -> float:
        """YES获胜概率（平台规则不同）"""
    def fetch_depth(self, rung) -> dict:
        """拿逐档深度，返回统一格式 {yes_bids, no_bids} 或能算成本的结构"""