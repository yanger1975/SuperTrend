import sys
import os
import argparse
import pandas as pd
import yfinance as yf
from datetime import datetime

from src.supertrend_ai.optimizer import optimize_supertrend_ai
from src.supertrend_ai.reporter import generate_supertrend_ai_report
from src.supertrend_ai.backtest import run_supertrend_ai_backtest
from src.data_loader import DataLoader

def main():
    parser = argparse.ArgumentParser(description="執行 SuperTrend AI 策略優化與回測")
    parser.add_argument("--ticker", type=str, default="QQQM", help="股票代號 (例如: QQQM, SPY)")
    parser.add_argument("--start", type=str, default="2021-08-01", help="回測起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-08-01", help="回測結束日期 (YYYY-MM-DD)")
    parser.add_argument("--out_dir", type=str, default="data/ai_reports", help="報告輸出目錄")
    
    args = parser.parse_args()
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始下載資料: {args.ticker} ({args.start} ~ {args.end})")
    loader = DataLoader()
    try:
        df = loader.fetch_data(args.ticker, start_date=args.start, end_date=args.end)
    except Exception as e:
        print(f"下載失敗: {e}")
        df = pd.DataFrame()
        
    if not df.empty:
        df.index = pd.to_datetime(df.index)
        df.dropna(inplace=True)
    
    if df.empty:
        print("資料下載失敗或為空，請檢查代號或日期範圍。")
        return
        
    # 判斷是否為基金
    is_fund = args.ticker.endswith(".EZ") or args.ticker.endswith(".ez")
    asset_type = "fund" if is_fund else "stock"
        
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始執行參數優化 (Asset Type: {asset_type})...")
    res_df, best_params = optimize_supertrend_ai(
        df=df,
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        lengths=[10, 14, 20],
        min_mults=[1.0, 1.5, 2.0],
        max_mults=[3.0, 4.0, 5.0],
        steps=[0.5],
        perf_alphas=[5, 10.0, 20],
        clusters=['Best', 'Average'],
        update_freqs=[1],
        long_onlys=[True],
        asset_type=asset_type
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
        show_progress=True,
        asset_type=asset_type
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
    
    # 輸出目前狀態與建議
    print("\n================== 當前狀態建議 ==================")
    last_row = df_ind.iloc[-1]
    current_price = last_row['Close']
    trend_dir = last_row['Trend']
    st_line = last_row['SuperTrend_AI']
    
    print(f"最新收盤價 ({last_row.name.strftime('%Y-%m-%d')}): {current_price:.2f}")
    if trend_dir == 1:
        print(f"目前狀態: 【多單持有中】")
        print(f"建議防守(止損)點位: {st_line:.2f}")
    else:
        print(f"目前狀態: 【空手觀望】")
        print(f"建議突破(開倉)點位: {st_line:.2f}")
    print("==================================================\n")

if __name__ == "__main__":
    main()
