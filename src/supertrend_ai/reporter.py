import pandas as pd
import numpy as np
import os
from typing import List, Dict, Any
from src.backtest_engine import Trade

def _format_pct(val):
    if pd.isna(val):
        return "-"
    return f"{val * 100:.2f}%"

def _format_float(val, dec=2):
    if pd.isna(val):
        return "-"
    return f"{val:.{dec}f}"

def create_monthly_return_pivot(equity: pd.Series, benchmark: pd.Series) -> str:
    # 建立 df
    df = pd.DataFrame({'Strategy': equity, 'Benchmark': benchmark})
    
    # resample 至月最後一天
    monthly = df.resample('ME').last()
    
    # 計算月報酬率 (%)
    monthly_ret = monthly.pct_change().dropna() * 100
    
    monthly_ret['Year'] = monthly_ret.index.year
    monthly_ret['Month'] = monthly_ret.index.month
    
    strat_pivot = monthly_ret.pivot(index='Year', columns='Month', values='Strategy')
    bench_pivot = monthly_ret.pivot(index='Year', columns='Month', values='Benchmark')
    
    for m in range(1, 13):
        if m not in strat_pivot.columns:
            strat_pivot[m] = np.nan
            bench_pivot[m] = np.nan
            
    strat_pivot = strat_pivot.reindex(columns=range(1, 13))
    bench_pivot = bench_pivot.reindex(columns=range(1, 13))
    
    md = "## 逐月報酬率 (策略% vs B&H%)\n\n"
    md += "| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | YTD |\n"
    md += "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    
    for year in strat_pivot.index:
        row = f"| **{year}** "
        strat_ytd_val = 1.0
        bench_ytd_val = 1.0
        
        has_data = False
        for m in range(1, 13):
            s_val = strat_pivot.loc[year, m]
            b_val = bench_pivot.loc[year, m]
            
            if pd.isna(s_val):
                row += "| - "
            else:
                has_data = True
                strat_ytd_val *= (1 + s_val/100)
                bench_ytd_val *= (1 + b_val/100)
                row += f"| {s_val:.1f}% ({b_val:.1f}%) "
                
        if has_data:
            s_ytd = (strat_ytd_val - 1.0) * 100
            b_ytd = (bench_ytd_val - 1.0) * 100
            row += f"| **{s_ytd:.1f}% ({b_ytd:.1f}%)** |\n"
        else:
            row += f"| - |\n"
            
        md += row
        
    return md

def generate_supertrend_ai_report(
    ticker: str,
    start_date: str,
    end_date: str,
    df_ind: pd.DataFrame,
    trades: List[Trade],
    equity: pd.Series,
    benchmark: pd.Series,
    opt_results: pd.DataFrame,
    best_params: Dict[str, Any],
    report_dir: str
) -> str:
    
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{ticker}_AI.md")
    
    md = f"# {ticker} SuperTrend AI 優化回測報告\n\n"
    md += f"**執行日期**: {pd.Timestamp.now().strftime('%Y%m%d')}\n"
    md += f"**資料區間**: {start_date} ~ {end_date}\n\n"
    
    md += "## 最佳參數\n\n"
    md += f"- **ATR Length**: {best_params.get('atr_length')}\n"
    md += f"- **Factor Range**: {best_params.get('factor_min')} ~ {best_params.get('factor_max')} (Step: {best_params.get('factor_step')})\n"
    md += f"- **Perf Alpha**: {best_params.get('perf_alpha')}\n"
    md += f"- **Target Cluster**: {best_params.get('from_cluster')}\n"
    md += f"- **目標指標 (Custom Score)**: {_format_float(best_params.get('Custom Score'))}\n\n"
    
    md += "## 參數優化結果 - Top 5\n\n"
    md += "| ATR | Factor Min | Factor Max | Step | Alpha | Cluster | Custom Score | CAGR | Max Drawdown | Sharpe Ratio | Calmar Ratio | Win Rate | Profit Factor |\n"
    md += "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    
    top5 = opt_results.head(5) if not opt_results.empty else pd.DataFrame()
    for _, row in top5.iterrows():
        md += f"| {row.get('atr_length', '-')} "
        md += f"| {row.get('factor_min', '-')} "
        md += f"| {row.get('factor_max', '-')} "
        md += f"| {row.get('factor_step', '-')} "
        md += f"| {row.get('perf_alpha', '-')} "
        md += f"| {row.get('from_cluster', '-')} "
        md += f"| {_format_float(row.get('Custom Score'))} "
        md += f"| {_format_pct(row.get('CAGR'))} "
        md += f"| {_format_pct(row.get('Max Drawdown'))} "
        md += f"| {_format_float(row.get('Sharpe Ratio'))} "
        md += f"| {_format_float(row.get('Calmar Ratio'))} "
        md += f"| {_format_pct(row.get('Win Rate'))} "
        md += f"| {_format_float(row.get('Profit Factor'))} |\n"
        
    md += "\n"
    
    md += "## 績效與風險指標\n\n"
    md += "| 指標 | 數值 |\n"
    md += "|---|---|\n"
    md += f"| CAGR | {_format_pct(best_params.get('CAGR'))} |\n"
    md += f"| Max Drawdown | {_format_pct(best_params.get('Max Drawdown'))} |\n"
    md += f"| Sharpe Ratio | {_format_float(best_params.get('Sharpe Ratio'))} |\n"
    md += f"| Calmar Ratio | {_format_float(best_params.get('Calmar Ratio'))} |\n"
    md += f"| Win Rate | {_format_pct(best_params.get('Win Rate'))} |\n"
    md += f"| Profit Factor | {_format_float(best_params.get('Profit Factor'))} |\n"
    md += f"| 總交易次數 | {len([t for t in trades if t.is_closed])} |\n\n"
    
    md += create_monthly_return_pivot(equity, benchmark)
    md += "\n"
    
    md += "## 完整交易紀錄\n\n"
    md += "| 序號 | 方向 | 進場日期 | 進場價 | 出場日期 | 出場價 | 損益(%) | 離場原因 |\n"
    md += "|---|---|---|---|---|---|---|---|\n"
    
    for i, t in enumerate(trades, 1):
        ext_date = t.exit_date.strftime('%Y-%m-%d') if pd.notna(t.exit_date) else '-'
        ext_price = f"{t.exit_price:.2f}" if pd.notna(t.exit_price) else '-'
        md += f"| {i} | {t.direction} | {t.entry_date.strftime('%Y-%m-%d')} | {t.entry_price:.2f} "
        md += f"| {ext_date} | {ext_price} | {_format_pct(t.pnl_pct)} | {t.exit_reason} |\n"
        
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(md)
        
    return md
