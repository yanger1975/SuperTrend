import pandas as pd
from typing import List, Tuple, Dict, Any
from src.supertrend_ai.backtest import run_supertrend_ai_backtest, calculate_custom_score
from src.supertrend_ai.db_setup import save_supertrend_ai_params

def optimize_supertrend_ai(
    df: pd.DataFrame,
    ticker: str,
    start_date: str,
    end_date: str,
    lengths: List[int] = [10],
    min_mults: List[float] = [1.0],
    max_mults: List[float] = [5.0],
    steps: List[float] = [0.5],
    perf_alphas: List[float] = [10.0],
    clusters: List[str] = ['Best'],
    update_freqs: List[int] = [1],
    long_only: bool = True,
    target_metric: str = "Custom Score"
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    執行 SuperTrend AI 的參數網格掃描，並將最佳結果寫入資料庫。
    參數清單放置於函式簽章，供使用者在 notebook 或腳本頂部彈性呼叫。
    """
    results = []
    best_score = -float('inf')
    best_params = {}
    
    from tqdm.auto import tqdm
    
    # Pre-calculate valid combinations
    combinations = []
    for length in lengths:
        for min_m in min_mults:
            for max_m in max_mults:
                for step in steps:
                    for alpha in perf_alphas:
                        for cluster in clusters:
                            for freq in update_freqs:
                                if min_m < max_m:
                                    combinations.append((length, min_m, max_m, step, alpha, cluster, freq))
                                
    total_combs = len(combinations)
    print(f"總共需要測試 {total_combs} 組參數組合。")
    
    for length, min_m, max_m, step, alpha, cluster, freq in tqdm(combinations, desc="優化進度"):
        trades, equity, benchmark, df_ind, metrics = run_supertrend_ai_backtest(
            df=df,
            length=length,
            min_mult=min_m,
            max_mult=max_m,
            step=step,
            perf_alpha=alpha,
            from_cluster=cluster,
            update_freq=freq,
            long_only=long_only,
            show_progress=False # Disable inner progress bar during optimization to avoid clutter
        )
                            
        score = calculate_custom_score(metrics)
        
        res_item = {
            "atr_length": length,
            "factor_min": min_m,
            "factor_max": max_m,
            "factor_step": step,
            "perf_alpha": alpha,
            "from_cluster": cluster,
            "update_freq": freq,
            "Custom Score": score
        }
        res_item.update(metrics)
        results.append(res_item)
        
        if score > best_score:
            best_score = score
            best_params = res_item
                                
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values(by=target_metric, ascending=False).reset_index(drop=True)
        
        # 寫入資料庫
        best = res_df.iloc[0]
        save_supertrend_ai_params(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            atr_length=int(best["atr_length"]),
            factor_min=float(best["factor_min"]),
            factor_max=float(best["factor_max"]),
            factor_step=float(best["factor_step"]),
            perf_alpha=float(best["perf_alpha"]),
            from_cluster=str(best["from_cluster"]),
            update_freq=int(best["update_freq"]),
            custom_score=float(best["Custom Score"]),
            cagr=float(best.get("CAGR", 0)),
            max_drawdown=float(best.get("Max Drawdown", 0)),
            sharpe_ratio=float(best.get("Sharpe Ratio", 0)),
            calmar_ratio=float(best.get("Calmar Ratio", 0)),
            win_rate=float(best.get("Win Rate", 0)),
            profit_factor=float(best.get("Profit Factor", 0))
        )
        
    return res_df, best_params
