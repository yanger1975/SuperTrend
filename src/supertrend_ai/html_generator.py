#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SuperTrend AI HTML Dashboard Generator
======================================
零外部相依之純 Python 靜態網頁生成器。
讀取最新訊號與最適參數 JSON，渲染出自包含、深色科技風格、具備即時排序與搜尋互動的 GitHub Pages 儀表板。
"""

import os
import sys
import json
import html
import argparse
import webbrowser
from datetime import datetime
from typing import List, Dict, Any, Optional

# Ensure stdout supports UTF-8 (e.g. for printing emojis on Windows console)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 預設資料路徑
DEFAULT_SIGNALS_JSON = "data/latest_signals_ai.json"
DEFAULT_PARAMS_JSON = "data/optimized_params_ai.json"
DEFAULT_OUTPUT_HTML = "public/index.html"


def load_json_data(file_path: str) -> List[Dict[str, Any]]:
    """安全載入 JSON 檔案，不存在或解析失敗時回傳空串列。"""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"警告: 讀取 {file_path} 失敗: {e}")
        return []


def format_currency_value(val: Any, currency: str) -> str:
    """格式化價格與幣別。"""
    if val is None or val == "" or val == "-":
        return "-"
    try:
        f_val = float(val)
        return f"{currency}{f_val:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def format_pct(val: Any, show_plus: bool = True) -> str:
    """格式化百分比數值。"""
    if val is None or val == "" or val == "-":
        return "-"
    try:
        f_val = float(val)
        sign = "+" if show_plus and f_val > 0 else ""
        return f"{sign}{f_val:.2f}%"
    except (ValueError, TypeError):
        return str(val)


def generate_dashboard_html(
    signals: Optional[List[Dict[str, Any]]] = None,
    params: Optional[List[Dict[str, Any]]] = None,
    output_path: str = DEFAULT_OUTPUT_HTML,
    dashboard_title: str = "SuperTrend AI 策略監控儀表板"
) -> str:
    """
    生成自包含深色科技主題之 HTML 儀表板。
    """
    if signals is None:
        signals = load_json_data(DEFAULT_SIGNALS_JSON)
    if params is None:
        params = load_json_data(DEFAULT_PARAMS_JSON)

    # 標的名稱補全對照表 (由 signals 建立 ticker -> name)
    ticker_names = {}
    for s in signals:
        t = s.get("ticker", "")
        if t:
            ticker_names[t.upper()] = s.get("name", t)

    # 分割美股與台股/基金資料
    def is_tw(ticker: str) -> bool:
        t_up = ticker.upper()
        return t_up.endswith(".TW") or t_up.endswith(".EZ")

    us_signals = [s for s in signals if not is_tw(s.get("ticker", ""))]
    tw_signals = [s for s in signals if is_tw(s.get("ticker", ""))]

    us_params = [p for p in params if not is_tw(p.get("ticker", ""))]
    tw_params = [p for p in params if is_tw(p.get("ticker", ""))]

    # 預設排序：訊號依 Long 置頂且 distance_pct 降冪；參數依 custom_score 降冪
    us_signals.sort(key=lambda x: (0 if x.get("position") == "long" else 1, -float(x.get("distance_pct", 0.0))))
    tw_signals.sort(key=lambda x: (0 if x.get("position") == "long" else 1, -float(x.get("distance_pct", 0.0))))

    us_params.sort(key=lambda x: -float(x.get("custom_score", 0.0)))
    tw_params.sort(key=lambda x: -float(x.get("custom_score", 0.0)))

    # 統計指標
    total_signals = len(signals)
    long_count = sum(1 for s in signals if s.get("position") == "long")
    cash_count = total_signals - long_count
    all_dates = [s.get("date") for s in signals if s.get("date")]
    latest_market_date = max(all_dates) if all_dates else datetime.now().strftime("%Y-%m-%d")
    gen_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    # 渲染訊號表格 HTML 列
    def render_signals_rows(sig_list: List[Dict[str, Any]]) -> str:
        if not sig_list:
            return '<tr><td colspan="9" class="empty-state">暫無訊號資料</td></tr>'
        rows = []
        for s in sig_list:
            ticker = html.escape(str(s.get("ticker", "")))
            name = html.escape(str(s.get("name", ticker)))
            date = html.escape(str(s.get("date", "-")))
            curr = html.escape(str(s.get("currency", "$")))
            close_disp = format_currency_value(s.get("close"), curr)
            pos = str(s.get("position", "cash")).lower()
            is_long = (pos == "long")
            pos_badge = '<span class="badge badge-long">做多 (Long)</span>' if is_long else '<span class="badge badge-cash">觀望 (Wait)</span>'

            entry_ref = format_currency_value(s.get("entry_ref"), curr)
            exit_ref = format_currency_value(s.get("exit_ref"), curr)

            dist_val = s.get("distance_pct", 0.0)
            dist_disp = format_pct(dist_val, show_plus=True)
            dist_class = "text-green" if float(dist_val) >= 0 else "text-red"

            action = html.escape(str(s.get("action", "-")))

            rows.append(f"""            <tr data-ticker="{ticker}" data-name="{name}">
                <td class="font-mono font-bold text-accent">{ticker}</td>
                <td>{name}</td>
                <td class="font-mono text-muted">{date}</td>
                <td class="font-mono text-right" data-val="{s.get('close', 0)}">{close_disp}</td>
                <td class="text-center">{pos_badge}</td>
                <td class="font-mono text-right">{entry_ref}</td>
                <td class="font-mono text-right">{exit_ref}</td>
                <td class="font-mono text-right {dist_class}" data-val="{dist_val}">{dist_disp}</td>
                <td class="text-center font-mono text-xs">{action}</td>
            </tr>""")
        return "\n".join(rows)

    # 渲染參數表格 HTML 列
    def render_params_rows(param_list: List[Dict[str, Any]]) -> str:
        if not param_list:
            return '<tr><td colspan="11" class="empty-state">暫無參數資料</td></tr>'
        rows = []
        for p in param_list:
            t_raw = p.get("ticker", "")
            ticker = html.escape(str(t_raw))
            name = html.escape(str(ticker_names.get(t_raw.upper(), ticker)))
            atr = p.get("atr_length", "-")
            f_min = p.get("factor_min", "-")
            f_max = p.get("factor_max", "-")
            f_step = p.get("factor_step", "-")
            factor_range = f"{f_min}~{f_max} ({f_step})" if f_min != "-" else "-"
            alpha = p.get("perf_alpha", "-")
            cluster = html.escape(str(p.get("from_cluster", "-")))

            score = p.get("custom_score", 0.0)
            score_disp = f"{float(score):.2f}" if isinstance(score, (int, float)) else str(score)

            win_rate = p.get("win_rate", 0.0)
            win_rate_disp = f"{float(win_rate) * 100:.1f}%" if isinstance(win_rate, (int, float)) else str(win_rate)

            cagr = p.get("cagr", 0.0)
            cagr_disp = f"{float(cagr) * 100:+.1f}%" if isinstance(cagr, (int, float)) else str(cagr)
            cagr_class = "text-green" if float(cagr) >= 0 else "text-red"

            mdd = p.get("max_drawdown", 0.0)
            mdd_disp = f"{float(mdd) * 100:.1f}%" if isinstance(mdd, (int, float)) else str(mdd)

            sharpe = p.get("sharpe_ratio", 0.0)
            sharpe_disp = f"{float(sharpe):.2f}" if isinstance(sharpe, (int, float)) else str(sharpe)

            rows.append(f"""            <tr data-ticker="{ticker}" data-name="{name}">
                <td class="font-mono font-bold text-accent">{ticker}</td>
                <td>{name}</td>
                <td class="font-mono text-center">{atr}</td>
                <td class="font-mono text-center text-xs">{factor_range}</td>
                <td class="font-mono text-center">{alpha}</td>
                <td class="text-center font-mono text-xs">{cluster}</td>
                <td class="font-mono font-bold text-right text-highlight" data-val="{score}">{score_disp}</td>
                <td class="font-mono font-bold text-right" data-val="{win_rate}">{win_rate_disp}</td>
                <td class="font-mono text-right {cagr_class}" data-val="{cagr}">{cagr_disp}</td>
                <td class="font-mono text-right text-red" data-val="{mdd}">{mdd_disp}</td>
                <td class="font-mono text-right" data-val="{sharpe}">{sharpe_disp}</td>
            </tr>""")
        return "\n".join(rows)

    us_signals_html = render_signals_rows(us_signals)
    tw_signals_html = render_signals_rows(tw_signals)
    us_params_html = render_params_rows(us_params)
    tw_params_html = render_params_rows(tw_params)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(dashboard_title)}</title>
    <style>
        :root {{
            --bg-base: #0B0F19;
            --bg-card: #111827;
            --bg-card-alt: #1F2937;
            --bg-hover: #1E293B;
            --border: #334155;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --accent: #38BDF8;
            --accent-glow: rgba(56, 189, 248, 0.2);
            --green: #10B981;
            --green-glow: rgba(16, 185, 129, 0.2);
            --red: #F43F5E;
            --yellow: #F59E0B;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.5;
            padding: 24px 16px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        /* Header */
        header {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }}

        .header-title h1 {{
            font-size: 1.75rem;
            font-weight: 700;
            color: #FFFFFF;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .header-title .tag {{
            font-size: 0.75rem;
            background: linear-gradient(135deg, #2563EB, #38BDF8);
            color: #FFFFFF;
            padding: 2px 8px;
            border-radius: 9999px;
            font-weight: 600;
        }}

        .header-meta {{
            font-size: 0.875rem;
            color: var(--text-muted);
            text-align: right;
        }}

        /* Stat Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}

        .stat-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .stat-card .label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 600;
        }}

        .stat-card .value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-main);
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }}

        /* Controls */
        .controls {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
        }}

        .tabs {{
            display: flex;
            background: var(--bg-card);
            padding: 4px;
            border-radius: 10px;
            border: 1px solid var(--border);
        }}

        .tab-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px 20px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .tab-btn:hover {{
            color: var(--text-main);
        }}

        .tab-btn.active {{
            background: #2563EB;
            color: #FFFFFF;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.4);
        }}

        .search-box {{
            display: flex;
            align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 6px 14px;
            width: 100%;
            max-width: 320px;
        }}

        .search-box input {{
            background: transparent;
            border: none;
            color: var(--text-main);
            font-size: 0.9rem;
            outline: none;
            width: 100%;
        }}

        .search-box input::placeholder {{
            color: var(--text-muted);
        }}

        /* Section & Table */
        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
        }}

        .section-panel {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            margin-bottom: 28px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }}

        .panel-header {{
            padding: 16px 20px;
            background: var(--bg-card-alt);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .panel-header h2 {{
            font-size: 1.1rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .table-responsive {{
            overflow-x: auto;
            width: 100%;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            text-align: left;
        }}

        th {{
            background: #162032;
            color: var(--text-muted);
            padding: 12px 14px;
            font-weight: 600;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border);
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }}

        th:hover {{
            color: var(--accent);
            background: #1C273D;
        }}

        th .sort-icon {{
            margin-left: 4px;
            font-size: 0.7rem;
            opacity: 0.5;
        }}

        th.sorted-asc .sort-icon::after {{
            content: "▲";
            opacity: 1;
            color: var(--accent);
        }}

        th.sorted-desc .sort-icon::after {{
            content: "▼";
            opacity: 1;
            color: var(--accent);
        }}

        td {{
            padding: 12px 14px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.4);
            white-space: nowrap;
        }}

        tr:hover td {{
            background: var(--bg-hover);
        }}

        /* Badges & Highlights */
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }}

        .badge-long {{
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .badge-cash {{
            background: rgba(148, 163, 184, 0.15);
            color: #94A3B8;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }}

        .font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
        .font-bold {{ font-weight: 700; }}
        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}
        .text-accent {{ color: var(--accent); }}
        .text-highlight {{ color: #FBBF24; font-weight: 700; }}
        .text-green {{ color: #34D399; }}
        .text-red {{ color: #FB7185; }}
        .text-muted {{ color: var(--text-muted); }}
        .text-xs {{ font-size: 0.75rem; }}

        .empty-state {{
            text-align: center;
            padding: 32px;
            color: var(--text-muted);
            font-style: italic;
        }}

        footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        footer a {{
            color: var(--accent);
            text-decoration: none;
        }}

        footer a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-title">
                <h1>⚡ SuperTrend AI 策略監控儀表板 <span class="tag">動態尋優</span></h1>
            </div>
            <div class="header-meta">
                <div>📅 市場資料日：<strong class="font-mono text-accent">{latest_market_date}</strong></div>
                <div class="text-xs">🔄 最後構建：{gen_time_str}</div>
            </div>
        </header>

        <!-- Stats Overview -->
        <div class="stats-grid">
            <div class="stat-card">
                <span class="label">監控總標的數</span>
                <span class="value">{total_signals}</span>
            </div>
            <div class="stat-card">
                <span class="label">當前持倉 (Long)</span>
                <span class="value text-green">{long_count}</span>
            </div>
            <div class="stat-card">
                <span class="label">當前觀望 (Wait)</span>
                <span class="value text-muted">{cash_count}</span>
            </div>
            <div class="stat-card">
                <span class="label">多頭比例 (Exposure)</span>
                <span class="value text-accent">{f"{(long_count / total_signals * 100):.1f}%" if total_signals > 0 else "0.0%"}</span>
            </div>
        </div>

        <!-- Controls: Tabs & Search -->
        <div class="controls">
            <div class="tabs">
                <button class="tab-btn active" data-tab="tab-us" onclick="switchTab('tab-us')">🇺🇸 美股市場 ({len(us_signals)})</button>
                <button class="tab-btn" data-tab="tab-tw" onclick="switchTab('tab-tw')">🇹🇼 台股與國內基金 ({len(tw_signals)})</button>
            </div>
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 搜尋標的代碼或名稱..." onkeyup="filterTables()">
            </div>
        </div>

        <!-- Tab 1: US Market -->
        <div id="tab-us" class="tab-content active">
            <!-- US Signals Table -->
            <div class="section-panel">
                <div class="panel-header">
                    <h2>📊 美股市場最新訊號與價格</h2>
                    <span class="text-xs text-muted">依距出場/進場價排序</span>
                </div>
                <div class="table-responsive">
                    <table id="table-us-signals">
                        <thead>
                            <tr>
                                <th onclick="sortTable('table-us-signals', 0, 'str')">代碼 <span class="sort-icon"></span></th>
                                <th onclick="sortTable('table-us-signals', 1, 'str')">標的名稱 <span class="sort-icon"></span></th>
                                <th onclick="sortTable('table-us-signals', 2, 'str')">資料日期 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-signals', 3, 'num')">最新市價 <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-us-signals', 4, 'str')">倉位狀態 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-signals', 5, 'num')">進場參考價 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-signals', 6, 'num')">出場參考價 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-signals', 7, 'num')">距標 % <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-us-signals', 8, 'str')">動作 <span class="sort-icon"></span></th>
                            </tr>
                        </thead>
                        <tbody>
{us_signals_html}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- US Params Table -->
            <div class="section-panel">
                <div class="panel-header">
                    <h2>⚙️ 美股市場最適參數與評分</h2>
                    <span class="text-xs text-muted">依綜合評分 (Score) 降冪排序</span>
                </div>
                <div class="table-responsive">
                    <table id="table-us-params">
                        <thead>
                            <tr>
                                <th onclick="sortTable('table-us-params', 0, 'str')">代碼 <span class="sort-icon"></span></th>
                                <th onclick="sortTable('table-us-params', 1, 'str')">標的名稱 <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-us-params', 2, 'num')">ATR <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-us-params', 3, 'str')">Factor 範圍 <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-us-params', 4, 'num')">Alpha <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-us-params', 5, 'str')">群集 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-params', 6, 'num')">Score <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-params', 7, 'num')">Win Rate <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-params', 8, 'num')">CAGR <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-params', 9, 'num')">Max DD <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-us-params', 10, 'num')">Sharpe <span class="sort-icon"></span></th>
                            </tr>
                        </thead>
                        <tbody>
{us_params_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Tab 2: TW Market & Funds -->
        <div id="tab-tw" class="tab-content">
            <!-- TW Signals Table -->
            <div class="section-panel">
                <div class="panel-header">
                    <h2>📊 台股與國內基金最新訊號與價格</h2>
                    <span class="text-xs text-muted">依距出場/進場價排序</span>
                </div>
                <div class="table-responsive">
                    <table id="table-tw-signals">
                        <thead>
                            <tr>
                                <th onclick="sortTable('table-tw-signals', 0, 'str')">代碼 <span class="sort-icon"></span></th>
                                <th onclick="sortTable('table-tw-signals', 1, 'str')">標的名稱 <span class="sort-icon"></span></th>
                                <th onclick="sortTable('table-tw-signals', 2, 'str')">資料日期 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-signals', 3, 'num')">最新市價/淨值 <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-tw-signals', 4, 'str')">倉位狀態 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-signals', 5, 'num')">進場參考價 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-signals', 6, 'num')">出場參考價 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-signals', 7, 'num')">距標 % <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-tw-signals', 8, 'str')">動作 <span class="sort-icon"></span></th>
                            </tr>
                        </thead>
                        <tbody>
{tw_signals_html}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TW Params Table -->
            <div class="section-panel">
                <div class="panel-header">
                    <h2>⚙️ 台股與國內基金最適參數與評分</h2>
                    <span class="text-xs text-muted">依綜合評分 (Score) 降冪排序</span>
                </div>
                <div class="table-responsive">
                    <table id="table-tw-params">
                        <thead>
                            <tr>
                                <th onclick="sortTable('table-tw-params', 0, 'str')">代碼 <span class="sort-icon"></span></th>
                                <th onclick="sortTable('table-tw-params', 1, 'str')">標的名稱 <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-tw-params', 2, 'num')">ATR <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-tw-params', 3, 'str')">Factor 範圍 <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-tw-params', 4, 'num')">Alpha <span class="sort-icon"></span></th>
                                <th class="text-center" onclick="sortTable('table-tw-params', 5, 'str')">群集 <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-params', 6, 'num')">Score <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-params', 7, 'num')">Win Rate <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-params', 8, 'num')">CAGR <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-params', 9, 'num')">Max DD <span class="sort-icon"></span></th>
                                <th class="text-right" onclick="sortTable('table-tw-params', 10, 'num')">Sharpe <span class="sort-icon"></span></th>
                            </tr>
                        </thead>
                        <tbody>
{tw_params_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <footer>
            <p>SuperTrend AI 量化交易系統 · 自動由 GitHub Actions 每日構建並部署至 GitHub Pages</p>
        </footer>
    </div>

    <!-- Client-side Interactions -->
    <script>
        function switchTab(tabId) {{
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            const target = document.getElementById(tabId);
            if (target) target.classList.add('active');
            const btn = document.querySelector(`[data-tab="${{tabId}}"]`);
            if (btn) btn.classList.add('active');
            filterTables();
        }}

        function filterTables() {{
            const filter = document.getElementById('searchInput').value.trim().toUpperCase();
            const activeTab = document.querySelector('.tab-content.active');
            if (!activeTab) return;

            const rows = activeTab.querySelectorAll('tbody tr');
            rows.forEach(row => {{
                const ticker = row.getAttribute('data-ticker') || '';
                const name = row.getAttribute('data-name') || '';
                if (ticker.toUpperCase().includes(filter) || name.toUpperCase().includes(filter)) {{
                    row.style.display = '';
                }} else {{
                    row.style.display = 'none';
                }}
            }});
        }}

        const sortDirections = {{}};

        function sortTable(tableId, colIndex, type) {{
            const table = document.getElementById(tableId);
            if (!table) return;
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            if (rows.length === 0 || rows[0].classList.contains('empty-state')) return;

            const thList = table.querySelectorAll('th');
            thList.forEach((th, idx) => {{
                if (idx !== colIndex) {{
                    th.classList.remove('sorted-asc', 'sorted-desc');
                }}
            }});

            const currentDir = sortDirections[tableId + '_' + colIndex] || 'desc';
            const newDir = (currentDir === 'asc') ? 'desc' : 'asc';
            sortDirections[tableId + '_' + colIndex] = newDir;

            thList[colIndex].classList.remove('sorted-asc', 'sorted-desc');
            thList[colIndex].classList.add(newDir === 'asc' ? 'sorted-asc' : 'sorted-desc');

            rows.sort((a, b) => {{
                let cellA = a.children[colIndex];
                let cellB = b.children[colIndex];
                if (!cellA || !cellB) return 0;

                let valA = cellA.getAttribute('data-val');
                let valB = cellB.getAttribute('data-val');

                if (valA === null) valA = cellA.innerText.trim();
                if (valB === null) valB = cellB.innerText.trim();

                if (type === 'num') {{
                    let numA = parseFloat(valA.toString().replace(/[^0-9.-]/g, '')) || 0;
                    let numB = parseFloat(valB.toString().replace(/[^0-9.-]/g, '')) || 0;
                    return newDir === 'asc' ? (numA - numB) : (numB - numA);
                }} else {{
                    return newDir === 'asc'
                        ? valA.toString().localeCompare(valB.toString(), 'zh-Hant')
                        : valB.toString().localeCompare(valA.toString(), 'zh-Hant');
                }}
            }});

            rows.forEach(r => tbody.appendChild(r));
        }}
    </script>
</body>
</html>
"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="SuperTrend AI 靜態儀表板生成器")
    parser.add_argument("--signals", type=str, default=DEFAULT_SIGNALS_JSON, help="最新訊號 JSON 路徑")
    parser.add_argument("--params", type=str, default=DEFAULT_PARAMS_JSON, help="最適參數 JSON 路徑")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_HTML, help="輸出 HTML 檔案路徑")
    parser.add_argument("--open", action="store_true", help="生成後自動於瀏覽器開啟預覽")

    args = parser.parse_args()

    out_file = generate_dashboard_html(
        signals=load_json_data(args.signals),
        params=load_json_data(args.params),
        output_path=args.output
    )
    print(f"✅ 儀表板成功生成至：{os.path.abspath(out_file)}")

    if args.open:
        webbrowser.open(f"file://{os.path.abspath(out_file)}")


if __name__ == "__main__":
    main()
