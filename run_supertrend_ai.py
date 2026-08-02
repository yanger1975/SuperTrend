import sys
import os
import argparse
import pandas as pd
import yfinance as yf
from datetime import datetime

from src.supertrend_ai.optimizer import optimize_supertrend_ai
from src.supertrend_ai.reporter import generate_supertrend_ai_report
from src.supertrend_ai.backtest import run_supertrend_ai_backtest

def main():
    parser = argparse.ArgumentParser(description="執行 SuperTrend AI 策略優化與回測")
    parser.add_argument("--ticker", type=str, default="QQQM", help="股票代號 (例如: QQQM, SPY)")
    parser.add_argument("--start", type=str, default="2021-08-01", help="回測起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-08-01", help="回測結束日期 (YYYY-MM-DD)")
    parser.add_argument("--out_dir", type=str, default="data/ai_reports", help="報告輸出目錄")
    
    args = parser.parse_args()
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始下載資料: {args.ticker} ({args.start} ~ {args.end})")
    df = yf.download(args.ticker, start=args.start, end=args.end)
    
    # 處理 yfinance 可能回傳的多重索引
    import importlib
    if "pandas" in sys.modules and isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
        
    df.index = pd.to_datetime(df.index)
    df.dropna(inplace=True)
    
    if df.empty:
        print("資料下載失敗或為空，請檢查代號或日期範圍。")
        return
        
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始執行參數優化...")
    res_df, best_params = optimize_supertrend_ai(
        df=df,
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        lengths=[10, 15],
        min_mults=[1.0, 2.0],
        max_mults=[3.0, 4.0],
        steps=[0.5],
        perf_alphas=[10.0],
        clusters=['Best', 'Average'],
        update_freqs=[1, 5],
        long_onlys=[True, False]
    )
    
    print("\n最佳參數組合:")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
        
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 使用最佳參數產出詳細回測與報告...")
    trades, equity, benchmark, df_ind, metrics = run_supertrend_ai_backtest(
        df=df,
        length=best_params['atr_length'],
        min_mult=best_params['factor_min'],
        max_mult=best_params['factor_max'],
        step=best_params['factor_step'],
        perf_alpha=best_params['perf_alpha'],
        from_cluster=best_params['from_cluster'],
        update_freq=best_params['update_freq'],
        long_only=best_params.get('long_only', True),
        show_progress=True
    )
    
    # 建立目錄
    os.makedirs(args.out_dir, exist_ok=True)
    
    # 產出報告
    md_report = generate_supertrend_ai_report(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        df_ind=df_ind,
        trades=trades,
        equity=equity,
        benchmark=benchmark,
        opt_results=res_df,
        best_params=best_params,
        report_dir=args.out_dir
    )
    
    report_path = os.path.join(args.out_dir, f"{args.ticker}_AI_Report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_report)
        
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 回測完成！報告已儲存至: {report_path}")

if __name__ == "__main__":
    main()
