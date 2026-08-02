import argparse
import sys
from datetime import datetime

# Ensure UTF-8 output encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.dca_addon.config import AddOnRule, StrategyConfig
from src.dca_addon.engine import DCAAddOnBacktester
from src.dca_addon.metrics import evaluate_performance
from src.dca_addon.visualizer import generate_html_report
from src.data_loader import DataLoader


def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="ETF 定期定額 + 低檔加碼策略回測工具")
    parser.add_argument("--symbol", type=str, default="0050.TW", help="標的代碼 (例如 0050.TW)")
    parser.add_argument("--start", type=str, default="2020-01-01", help="歷史數據起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=today_str, help="歷史數據結束日期 (YYYY-MM-DD)")
    parser.add_argument("--amount", type=float, default=10000, help="每期定期定額金額")
    parser.add_argument("--budget", type=float, default=500000, help="額外加碼總預算")
    parser.add_argument("--output", type=str, default="dca_backtest_report.html", help="輸出 HTML 報告檔案名稱")

    args = parser.parse_args()

    # 安全驗證 output 檔案名稱
    output_filename = os.path.basename(args.output)
    if not output_filename.endswith(".html"):
        output_filename += ".html"

    loader = DataLoader()
    try:
        df = loader.fetch_data(ticker=args.symbol, start_date=args.start, end_date=args.end, interval="1d")
    except Exception as e:
        print(f"錯誤：讀取標的 {args.symbol} 數據失敗：{e}")
        sys.exit(1)

    if df.empty:
        print(f"錯誤：找不到標的 {args.symbol} 的歷史數據。")
        sys.exit(1)

    config = StrategyConfig(
        base_invest_amount=args.amount,
        rules=[
            AddOnRule(lookback_days=20, drawdown_threshold=0.06, multiplier=2.0),
            AddOnRule(lookback_days=20, drawdown_threshold=0.12, multiplier=3.0),
        ],
        cooldown_days=5,
        max_addons_per_month=2,
        total_extra_budget=args.budget
    )

    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()
    metrics = evaluate_performance(equity, trades, config)

    generate_html_report(df, equity, trades, metrics, output_filename, config=config)

    print(f"回測完成！報告已儲存至：{output_filename}")
    print(f"總報酬率: {metrics['total_return']:.2%}, 最大回撤: {metrics['max_drawdown']:.2%}, Alpha: {metrics['alpha_vs_pure_dca']:.2%}")


if __name__ == "__main__":
    main()
