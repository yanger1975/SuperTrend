from typing import List, Tuple, Dict, Any, Optional
import pandas as pd
import numpy as np
from src.dca_addon.config import StrategyConfig, AddOnRule


class DCAAddOnBacktester:
    def __init__(self, df: pd.DataFrame, config: StrategyConfig):
        df_copy = df.copy()
        if "Date" not in df_copy.columns:
            if "datetime" in df_copy.columns:
                df_copy = df_copy.rename(columns={"datetime": "Date"})
            else:
                df_copy = df_copy.reset_index()
                dt_cols = [c for c in df_copy.columns if "date" in str(c).lower() or "time" in str(c).lower()]
                if dt_cols:
                    df_copy = df_copy.rename(columns={dt_cols[0]: "Date"})
                else:
                    df_copy = df_copy.rename(columns={df_copy.columns[0]: "Date"})

        self.df = df_copy.sort_values("Date").reset_index(drop=True)
        self.config = config
        self.trades: List[Dict[str, Any]] = []


    def prepare_data(self) -> None:
        self.df["Date"] = pd.to_datetime(self.df["Date"])
        self.df["year_month"] = self.df["Date"].dt.to_period("M")

        for i, rule in enumerate(self.config.rules):
            col_name = f"ret_rule_{i}"
            if rule.reference_type == "high":
                rolling_high = self.df["Close"].rolling(window=rule.lookback_days, min_periods=1).max()
                self.df[col_name] = self.df["Close"] / rolling_high - 1.0
            else:
                self.df[col_name] = self.df["Close"] / self.df["Close"].shift(rule.lookback_days) - 1.0

    def is_regular_invest_day(self, idx: int) -> bool:
        if idx == 0:
            return True
        curr_month = self.df.loc[idx, "year_month"]
        prev_month = self.df.loc[idx - 1, "year_month"]
        return curr_month != prev_month

    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        self.prepare_data()

        total_units = 0.0
        total_cost = 0.0
        extra_budget_used = 0.0
        last_addon_idx = -999999
        monthly_addon_count: Dict[Any, int] = {}
        portfolio_values = []

        for idx, row in self.df.iterrows():
            date = row["Date"]
            price = float(row["Close"])
            ym = row["year_month"]

            # 1. 定期定額扣款
            if self.is_regular_invest_day(idx):
                amount = self.config.base_invest_amount
                # 總投入限制檢查
                if self.config.max_total_invest is not None:
                    remaining = self.config.max_total_invest - total_cost
                    amount = min(amount, max(0.0, remaining))

                if amount > 0:
                    units = amount / price
                    total_units += units
                    total_cost += amount
                    self.trades.append({
                        "Date": date,
                        "Type": "regular",
                        "Price": price,
                        "Amount": amount,
                        "Units": units
                    })

            # 2. 低檔加碼觸發
            eligible_rules = []
            for i, rule in enumerate(self.config.rules):
                ret_col = f"ret_rule_{i}"
                ret = row[ret_col]
                if pd.notna(ret) and ret <= -rule.drawdown_threshold:
                    eligible_rules.append(rule)

            if eligible_rules:
                # 取跌幅門檻最深者
                selected_rule = max(eligible_rules, key=lambda r: r.drawdown_threshold)

                # 冷卻天數檢查
                if idx - last_addon_idx <= self.config.cooldown_days:
                    selected_rule = None

                # 每月次數上限檢查
                curr_count = monthly_addon_count.get(ym, 0)
                if (
                    selected_rule is not None
                    and self.config.max_addons_per_month is not None
                    and curr_count >= self.config.max_addons_per_month
                ):
                    selected_rule = None

                if selected_rule is not None:
                    addon_amount = self.config.base_invest_amount * selected_rule.multiplier

                    # 額外加碼預算檢查
                    if self.config.total_extra_budget is not None:
                        if extra_budget_used + addon_amount > self.config.total_extra_budget:
                            addon_amount = max(0.0, self.config.total_extra_budget - extra_budget_used)

                    # 總投入資金上限檢查
                    if self.config.max_total_invest is not None:
                        remaining = self.config.max_total_invest - total_cost
                        addon_amount = min(addon_amount, max(0.0, remaining))

                    if addon_amount > 0:
                        units = addon_amount / price
                        total_units += units
                        total_cost += addon_amount
                        extra_budget_used += addon_amount
                        last_addon_idx = idx
                        monthly_addon_count[ym] = curr_count + 1
                        self.trades.append({
                            "Date": date,
                            "Type": "addon",
                            "Price": price,
                            "Amount": addon_amount,
                            "Units": units,
                            "RuleLookback": selected_rule.lookback_days,
                            "RuleThreshold": selected_rule.drawdown_threshold,
                            "RuleMultiplier": selected_rule.multiplier,
                        })

            market_value = total_units * price
            avg_cost = total_cost / total_units if total_units > 0 else 0.0
            unrealized_pnl = market_value - total_cost
            ret = market_value / total_cost - 1.0 if total_cost > 0 else 0.0

            portfolio_values.append({
                "Date": date,
                "Close": price,
                "TotalUnits": total_units,
                "TotalCost": total_cost,
                "MarketValue": market_value,
                "AvgCost": avg_cost,
                "UnrealizedPnL": unrealized_pnl,
                "Return": ret
            })

        equity = pd.DataFrame(portfolio_values)
        trades = pd.DataFrame(self.trades) if self.trades else pd.DataFrame(
            columns=["Date", "Type", "Price", "Amount", "Units"]
        )
        return equity, trades
