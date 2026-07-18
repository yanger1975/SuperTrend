import pandas as pd
from typing import List, Dict, Any, Tuple
from src.backtest_engine import BacktestEngine
from src.risk_manager import RiskManager
from src.indicators import compute_supertrend, compute_hma

class ParameterOptimizer:
    """
    網格參數搜尋優化器
    支援 Train/Test (樣本外) 劃分驗證、參數高原分析，以及自定義綜合評分排行。
    """
    def __init__(self, raw_df: pd.DataFrame):
        self.raw_df = raw_df

    def calculate_custom_score(self, metrics: Dict[str, Any]) -> float:
        """
        評估穩健性的綜合評分公式：
        Score = 0.35 * Sharpe + 0.25 * Calmar + 0.20 * PF - 0.20 * |MaxDD|
        """
        sharpe = metrics.get("Sharpe Ratio", 0.0)
        calmar = metrics.get("Calmar Ratio", 0.0)
        pf = metrics.get("Profit Factor", 1.0)
        max_dd = abs(metrics.get("Max Drawdown", 0.0))
        return 0.35 * sharpe + 0.25 * calmar + 0.20 * pf - 0.20 * max_dd

    def optimize(self,
                 st_periods: List[int],
                 st_multipliers: List[float],
                 ma_periods: List[int],
                 target_metric: str = "Custom Score",
                 train_ratio: float = 1.0  # 1.0 代表不進行樣本外 (OOS) 切割
                 ) -> Tuple[pd.DataFrame, pd.DataFrame]:

        # 計算分割索引（基於原始資料長度）
        split_idx = int(len(self.raw_df) * train_ratio)

        train_results = []
        test_results = []

        for period in st_periods:
            for mult in st_multipliers:
                # ===== 修正：先在完整資料上計算 SuperTrend =====
                # 避免遞迴指標在不同資料長度下產生不同的計算結果
                df_st_full, _ = compute_supertrend(self.raw_df, period=period, multiplier=mult)

                # 再依據 train_ratio 切分 Train/Test
                df_st_train = df_st_full.iloc[:split_idx].copy()
                df_st_test = df_st_full.iloc[split_idx:].copy() if train_ratio < 1.0 else pd.DataFrame()

                for ma_p in ma_periods:
                    # A. 樣本內 (Train) 回測與優化
                    df_temp_train = df_st_train.copy()
                    df_temp_train["HMA"] = compute_hma(df_temp_train["Close"], period=ma_p)
                    df_temp_train["MA_Filter"] = df_temp_train["Close"] > df_temp_train["HMA"]

                    engine_train = BacktestEngine(df_temp_train)
                    trades_train, eq_train, _ = engine_train.run(long_only=True)
                    rm_train = RiskManager(trades_train, eq_train)
                    metrics_train = rm_train.calculate_metrics()

                    if metrics_train:
                        score_train = self.calculate_custom_score(metrics_train)
                        result_item = {
                            "ST_Period": period,
                            "ST_Multiplier": mult,
                            "MA_Period": ma_p,
                            "Custom Score": score_train
                        }
                        result_item.update(metrics_train)
                        train_results.append(result_item)

                    # B. 樣本外 (Test) 驗證
                    if not df_st_test.empty:
                        df_temp_test = df_st_test.copy()
                        df_temp_test["HMA"] = compute_hma(df_temp_test["Close"], period=ma_p)
                        df_temp_test["MA_Filter"] = df_temp_test["Close"] > df_temp_test["HMA"]

                        engine_test = BacktestEngine(df_temp_test)
                        trades_test, eq_test, _ = engine_test.run(long_only=True)
                        rm_test = RiskManager(trades_test, eq_test)
                        metrics_test = rm_test.calculate_metrics()

                        if metrics_test:
                            score_test = self.calculate_custom_score(metrics_test)
                            result_item_test = {
                                "ST_Period": period,
                                "ST_Multiplier": mult,
                                "MA_Period": ma_p,
                                "Custom Score": score_test
                            }
                            result_item_test.update(metrics_test)
                            test_results.append(result_item_test)

        train_res_df = pd.DataFrame(train_results)
        test_res_df = pd.DataFrame(test_results)

        # 依目標指標排序並重置 Index
        if not train_res_df.empty:
            train_res_df = train_res_df.sort_values(by=target_metric, ascending=False).reset_index(drop=True)
        if not test_res_df.empty:
            test_res_df = test_res_df.sort_values(by=target_metric, ascending=False).reset_index(drop=True)

        return train_res_df, test_res_df
