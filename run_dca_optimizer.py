import argparse
import sys
from datetime import datetime

# Ensure UTF-8 output encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.dca_addon.optimizer import grid_search
from src.data_loader import DataLoader


def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="ETF 低檔加碼策略參數最佳化工具")
    parser.add_argument("--symbol", type=str, default="0050.TW", help="標的代碼")
    parser.add_argument("--start", type=str, default="2020-01-01", help="歷史數據起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=today_str, help="歷史數據結束日期 (YYYY-MM-DD)")
    args = parser.parse_args()

    loader = DataLoader()
    try:
        df = loader.fetch_data(ticker=args.symbol, start_date=args.start, end_date=args.end, interval="1d")
    except Exception as e:
        print(f"錯誤：讀取標的 {args.symbol} 數據失敗：{e}")
        sys.exit(1)

    if df.empty:
        print(f"錯誤：找不到標的 {args.symbol} 的數據。")
        return

    print("開始執行參數網格掃描...")
    param_grid = {
        "lookbacks": [10, 20, 60],
        "first_thresholds": [0.05, 0.06, 0.08],
        "second_thresholds": [0.10, 0.12, 0.15],
        "first_multipliers": [1.5, 2.0],
        "second_multipliers": [2.0, 3.0],
        "cooldowns": [0, 3, 5],
        "monthly_limits": [1, 2]
    }

    results_df = grid_search(df, param_grid)
    results_df = results_df.sort_values("total_return", ascending=False)
    results_df.to_csv("dca_optimization_results.csv", index=False, encoding="utf-8-sig")
    print(f"最佳化完成！前 5 名參數組合：\n", results_df.head())


if __name__ == "__main__":
    main()
