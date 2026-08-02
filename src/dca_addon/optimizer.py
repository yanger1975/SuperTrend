from itertools import product
from typing import Dict, Any, List
import pandas as pd
from src.dca_addon.config import AddOnRule, StrategyConfig
from src.dca_addon.engine import DCAAddOnBacktester
from src.dca_addon.metrics import evaluate_performance


def grid_search(
    df: pd.DataFrame,
    param_grid: Dict[str, List[Any]],
    base_amount: float = 10000.0,
    total_extra_budget: float = 500000.0
) -> pd.DataFrame:
    records = []

    lookbacks = param_grid.get("lookbacks", [10, 20])
    t1_list = param_grid.get("first_thresholds", [0.05, 0.08])
    t2_list = param_grid.get("second_thresholds", [0.10, 0.12])
    m1_list = param_grid.get("first_multipliers", [1.5, 2.0])
    m2_list = param_grid.get("second_multipliers", [2.0, 3.0])
    cooldowns = param_grid.get("cooldowns", [0, 3])
    monthly_limits = param_grid.get("monthly_limits", [1, 2])

    for lb, t1, t2, m1, m2, cd, ml in product(
        lookbacks, t1_list, t2_list, m1_list, m2_list, cooldowns, monthly_limits
    ):
        if t2 <= t1 or m2 < m1:
            continue

        config = StrategyConfig(
            base_invest_amount=base_amount,
            rules=[
                AddOnRule(lookback_days=lb, drawdown_threshold=t1, multiplier=m1),
                AddOnRule(lookback_days=lb, drawdown_threshold=t2, multiplier=m2),
            ],
            cooldown_days=cd,
            max_addons_per_month=ml,
            total_extra_budget=total_extra_budget
        )

        bt = DCAAddOnBacktester(df, config)
        equity, trades = bt.run()
        perf = evaluate_performance(equity, trades, config)

        records.append({
            "lookback": lb,
            "t1": t1,
            "t2": t2,
            "m1": m1,
            "m2": m2,
            "cooldown": cd,
            "monthly_limit": ml,
            **perf
        })

    return pd.DataFrame(records)
