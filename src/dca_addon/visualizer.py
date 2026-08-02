from typing import Dict, Any, Optional
import logging
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.dca_addon.config import StrategyConfig

logger = logging.getLogger(__name__)


def plot_dca_summary(
    df: Optional[pd.DataFrame] = None,
    equity: Optional[pd.DataFrame] = None,
    trades: Optional[pd.DataFrame] = None
) -> go.Figure:
    """
    繪製 DCA + 低檔加碼策略回測綜合視覺化圖表。
    """
    if equity is None or equity.empty:
        fig = go.Figure()
        fig.update_layout(title="無有效回測數據可進行視覺化圖表繪製")
        return fig

    if trades is None:
        trades = pd.DataFrame()

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(
            "標的價格與加碼點位散點圖",
            "累計投入資金 vs 市場總市值",
            "平均持倉成本 vs 市場價格 (Underwater)"
        )
    )

    # Subplot 1: Price & Addon triggers
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["Close"],
            name="Close Price",
            line=dict(color="#2563eb", width=1.5)
        ),
        row=1, col=1
    )

    if not trades.empty and "Type" in trades.columns:
        addon_trades = trades[trades["Type"] == "addon"].copy()
        if not addon_trades.empty:
            addon_trades["Date_str"] = pd.to_datetime(addon_trades["Date"]).dt.strftime("%Y-%m-%d")
            hover_texts = [
                f"日期: {r['Date_str']}<br>"
                f"加碼觸發價: ${r['Price']:.2f}<br>"
                f"加碼金額: ${r['Amount']:,.0f}<br>"
                f"買入股數: {r['Units']:.2f}<br>"
                f"規則: 跌 {r.get('RuleThreshold', 0):.0%} 加 {r.get('RuleMultiplier', 1)} 倍"
                for _, r in addon_trades.iterrows()
            ]

            fig.add_trace(
                go.Scatter(
                    x=addon_trades["Date"],
                    y=addon_trades["Price"],
                    mode="markers",
                    name="AddOn Trigger",
                    marker=dict(symbol="triangle-up", size=14, color="#dc2626", line=dict(width=1, color="black")),
                    text=hover_texts,
                    hoverinfo="text"
                ),
                row=1, col=1
            )

    # Subplot 2: Total Cost vs Market Value
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["TotalCost"],
            name="Total Cost",
            line=dict(color="#6b7280", dash="dash", width=1.5)
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["MarketValue"],
            name="Market Value",
            line=dict(color="#16a34a", width=2)
        ),
        row=2, col=1
    )

    # Subplot 3: Avg Cost vs Close Price
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["AvgCost"],
            name="Avg Cost",
            line=dict(color="#ea580c", width=2)
        ),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["Close"],
            name="Close",
            opacity=0.35,
            line=dict(color="#2563eb", width=1)
        ),
        row=3, col=1
    )

    fig.update_layout(
        height=850,
        title_text="DCA + 低檔加碼策略回測綜合視覺化圖表",
        showlegend=True,
        template="plotly_white"
    )
    return fig


def generate_html_report(
    df: Optional[pd.DataFrame],
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    metrics: Dict[str, Any],
    output_filename: str,
    config: Optional[StrategyConfig] = None
) -> None:
    """
    產生包含 KPI 數據卡片、圖表與交易紀錄的獨立 HTML 回測報告。
    """
    fig = plot_dca_summary(df, equity, trades)
    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    total_return_str = f"{metrics.get('total_return', 0):.2%}" if isinstance(metrics.get('total_return'), float) else "0.00%"
    cagr_str = f"{metrics.get('cagr', 0):.2%}" if isinstance(metrics.get('cagr'), float) else "0.00%"
    mdd_str = f"{metrics.get('max_drawdown', 0):.2%}" if isinstance(metrics.get('max_drawdown'), float) else "0.00%"
    alpha_str = f"{metrics.get('alpha_vs_pure_dca', 0):.2%}" if isinstance(metrics.get('alpha_vs_pure_dca'), float) else "0.00%"
    utilization_str = f"{metrics.get('extra_budget_utilization_rate', 0):.1%}" if isinstance(metrics.get('extra_budget_utilization_rate'), float) else "0.0%"

    kpi_cards = f"""
    <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 25px;">
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; flex: 1; min-width: 150px;">
            <div style="color: #64748b; font-size: 14px;">總回報率</div>
            <div style="font-size: 22px; font-weight: 700; color: #0f172a; margin-top: 4px;">{total_return_str}</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; flex: 1; min-width: 150px;">
            <div style="color: #64748b; font-size: 14px;">年化報酬 (CAGR)</div>
            <div style="font-size: 22px; font-weight: 700; color: #0f172a; margin-top: 4px;">{cagr_str}</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; flex: 1; min-width: 150px;">
            <div style="color: #64748b; font-size: 14px;">最大回撤 (MDD)</div>
            <div style="font-size: 22px; font-weight: 700; color: #dc2626; margin-top: 4px;">{mdd_str}</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; flex: 1; min-width: 150px;">
            <div style="color: #64748b; font-size: 14px;">Alpha (超越純DCA)</div>
            <div style="font-size: 22px; font-weight: 700; color: #16a34a; margin-top: 4px;">{alpha_str}</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; flex: 1; min-width: 150px;">
            <div style="color: #64748b; font-size: 14px;">加碼次數</div>
            <div style="font-size: 22px; font-weight: 700; color: #2563eb; margin-top: 4px;">{metrics.get('addon_count', 0)} 次</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; flex: 1; min-width: 150px;">
            <div style="color: #64748b; font-size: 14px;">加碼預算使用率</div>
            <div style="font-size: 22px; font-weight: 700; color: #0f172a; margin-top: 4px;">{utilization_str}</div>
        </div>
    </div>
    """

    # 1. 策略參數摘要
    config_html = ""
    if config:
        rules_list = []
        for i, r in enumerate(config.rules, 1):
            ref_type_name = "N日最高價" if r.reference_type == "high" else "N日前收盤價"
            rules_list.append(f"階梯 {i}: 比較 {r.lookback_days} 日 ({ref_type_name})，跌幅 &ge; {r.drawdown_threshold:.0%} 時，加碼原扣款金額之 {r.multiplier} 倍；")
        rules_str = "".join(rules_list)

        extra_budget_str = f"${config.total_extra_budget:,.0f}" if config.total_extra_budget else '無限制'
        max_addons_str = f"{config.max_addons_per_month}" if config.max_addons_per_month else '無限制'

        config_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
            <h3 style="margin-top: 0; color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">⚙️ 策略設定參數</h3>
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <tr>
                    <td style="padding: 6px; font-weight: bold; width: 150px;">定期定額金額:</td>
                    <td style="padding: 6px;">${config.base_invest_amount:,.0f} / 期</td>
                    <td style="padding: 6px; font-weight: bold; width: 150px;">額外加碼總預算:</td>
                    <td style="padding: 6px;">{extra_budget_str}</td>
                </tr>
                <tr>
                    <td style="padding: 6px; font-weight: bold;">冷卻天數 (Cooldown):</td>
                    <td style="padding: 6px;">{config.cooldown_days} 天</td>
                    <td style="padding: 6px; font-weight: bold;">每月加碼次數限制:</td>
                    <td style="padding: 6px;">{max_addons_str} 次</td>
                </tr>
                <tr>
                    <td style="padding: 6px; font-weight: bold;">加碼觸發規則:</td>
                    <td style="padding: 6px;" colspan="3">{rules_str if rules_str else '無定義加碼規則'}</td>
                </tr>
            </table>
        </div>
        """

    # 2. 加碼交易明細表格
    addon_trades = trades[trades["Type"] == "addon"].copy() if not trades.empty and "Type" in trades.columns else pd.DataFrame()
    if not addon_trades.empty:
        addon_rows_list = []
        for idx, row in addon_trades.iterrows():
            dt_str = pd.to_datetime(row["Date"]).strftime("%Y-%m-%d")
            price = row["Price"]
            amount = row["Amount"]
            units = row["Units"]
            lookback = row.get("RuleLookback", "-")
            threshold = f"{row.get('RuleThreshold', 0):.0%}" if "RuleThreshold" in row else "-"
            multiplier = f"{row.get('RuleMultiplier', 1)}x" if "RuleMultiplier" in row else "-"

            addon_rows_list.append(f"""
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px; text-align: center;">{dt_str}</td>
                <td style="padding: 10px; text-align: right;">${price:,.2f}</td>
                <td style="padding: 10px; text-align: right; font-weight: bold; color: #dc2626;">${amount:,.0f}</td>
                <td style="padding: 10px; text-align: right;">{units:,.2f}</td>
                <td style="padding: 10px; text-align: center;">{lookback} 日</td>
                <td style="padding: 10px; text-align: center;">{threshold}</td>
                <td style="padding: 10px; text-align: center; font-weight: bold;">{multiplier}</td>
            </tr>
            """)
        addon_rows = "".join(addon_rows_list)

        trades_table_html = f"""
        <div style="background: #ffffff; border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px; margin-top: 25px;">
            <h3 style="margin-top: 0; color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">📌 低檔加碼觸發明細紀錄 ({len(addon_trades)} 筆)</h3>
            <div style="max-height: 400px; overflow-y: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 14px; text-align: left;">
                    <thead>
                        <tr style="background: #f8fafc; border-bottom: 2px solid #cbd5e1; color: #475569;">
                            <th style="padding: 10px; text-align: center;">加碼日期</th>
                            <th style="padding: 10px; text-align: right;">觸發成交價</th>
                            <th style="padding: 10px; text-align: right;">加碼金額</th>
                            <th style="padding: 10px; text-align: right;">購入股數</th>
                            <th style="padding: 10px; text-align: center;">比較天數</th>
                            <th style="padding: 10px; text-align: center;">跌幅門檻</th>
                            <th style="padding: 10px; text-align: center;">加碼倍數</th>
                        </tr>
                    </thead>
                    <tbody>
                        {addon_rows}
                    </tbody>
                </table>
            </div>
        </div>
        """
    else:
        trades_table_html = """
        <div style="background: #ffffff; border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px; margin-top: 25px;">
            <h3 style="margin-top: 0; color: #1e293b;">📌 低檔加碼觸發明細紀錄</h3>
            <p style="color: #64748b;">此回測區間內未符合低檔加碼條件，無任何加碼紀錄。</p>
        </div>
        """

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>ETF 低檔加碼策略回測報告</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 30px; background-color: #f1f5f9; color: #334155; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2 style="color: #0f172a; margin-bottom: 20px;">📊 ETF 定期定額 + 低檔加碼策略回測報告</h2>
            {config_html}
            {kpi_cards}
            <div style="background: #ffffff; border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px;">{chart_html}</div>
            {trades_table_html}
        </div>
    </body>
    </html>
    """

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(full_html)
    except OSError as e:
        logger.error("無法寫入 HTML 報告至 %s: %s", output_filename, e)
