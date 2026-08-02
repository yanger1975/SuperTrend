from dataclasses import dataclass, field
from typing import List, Optional, Literal


@dataclass
class AddOnRule:
    lookback_days: int
    drawdown_threshold: float  # 例如 0.06 代表跌 6%
    multiplier: float          # 例如 2.0 代表為原定期定額金額的 2 倍
    reference_type: Literal["shift", "high"] = "shift"  # 'shift': N日前收盤價, 'high': N日最高價


@dataclass
class StrategyConfig:
    base_invest_amount: float
    rules: List[AddOnRule] = field(default_factory=list)
    invest_frequency: str = "M"                   # 'M' 代表每月
    cooldown_days: int = 0                       # 觸發後冷卻天數
    max_addons_per_month: Optional[int] = None    # 每月加碼次數上限
    total_extra_budget: Optional[float] = None     # 額外加碼總預算上限
    max_total_invest: Optional[float] = None      # 總投入金額上限
    cash_risk_free_rate: float = 0.0             # 未投入現金無風險年利率
