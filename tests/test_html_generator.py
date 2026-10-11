# -*- coding: utf-8 -*-
import os
import subprocess
import pytest
from src.supertrend_ai.html_generator import generate_dashboard_html

def test_generate_dashboard_html_content(tmp_path):
    out_html = str(tmp_path / "index.html")
    signals = [
        {
            "ticker": "SPY",
            "name": "SPDR S&P 500 ETF Trust",
            "market": "us",
            "is_fund": False,
            "date": "2026-10-10",
            "close": 580.0,
            "currency": "$",
            "position": "long",
            "entry_ref": 570.0,
            "exit_ref": 575.0,
            "distance_pct": 0.87,
            "action": "HOLD_LONG"
        },
        {
            "ticker": "0050.TW",
            "name": "元大台灣50",
            "market": "tw",
            "is_fund": False,
            "date": "2026-10-11",
            "close": 195.5,
            "currency": "NT$",
            "position": "long",
            "entry_ref": 188.0,
            "exit_ref": 190.0,
            "distance_pct": 2.89,
            "action": "HOLD_LONG"
        },
        {
            "ticker": "33YTW.EZ",
            "name": "統一全球新科技基金",
            "market": "tw",
            "is_fund": True,
            "date": "2026-10-11",
            "close": 42.15,
            "currency": "NT$",
            "position": "cash",
            "entry_ref": 43.0,
            "exit_ref": "-",
            "distance_pct": -1.98,
            "action": "WAIT_CASH"
        }
    ]

    params = [
        {
            "ticker": "SPY",
            "atr_length": 10,
            "factor_min": 2.0,
            "factor_max": 5.0,
            "factor_step": 0.5,
            "perf_alpha": 10.0,
            "from_cluster": "Top",
            "custom_score": 12.5,
            "win_rate": 0.85,
            "cagr": 0.185,
            "max_drawdown": -0.095,
            "sharpe_ratio": 1.75
        },
        {
            "ticker": "0050.TW",
            "atr_length": 10,
            "factor_min": 2.0,
            "factor_max": 5.0,
            "factor_step": 0.5,
            "perf_alpha": 20.0,
            "from_cluster": "Average",
            "custom_score": 4.81,
            "win_rate": 0.875,
            "cagr": 0.265,
            "max_drawdown": -0.151,
            "sharpe_ratio": 1.43
        }
    ]

    result_path = generate_dashboard_html(signals, params, output_path=out_html)
    assert os.path.exists(result_path)

    with open(result_path, "r", encoding="utf-8") as f:
        html_text = f.read()

    # Core titles and themes
    assert "SuperTrend AI" in html_text
    assert "最新訊號" in html_text
    assert "最適參數" in html_text
    assert "Score" in html_text
    assert "Win Rate" in html_text

    # Check tickers and values
    assert "SPY" in html_text
    assert "0050.TW" in html_text
    assert "33YTW.EZ" in html_text
    assert "統一全球新科技基金" in html_text
    assert "12.50" in html_text or "12.5" in html_text
    assert "87.5%" in html_text or "87.50%" in html_text or "0.875" in html_text

    # Tab navigation and table sorting elements
    assert "tab-btn" in html_text
    assert "switchTab" in html_text or "data-tab" in html_text
    assert "sortTable" in html_text or "data-sort" in html_text

    # Anti-SEO and privacy assertions
    assert 'name="robots" content="noindex, nofollow' in html_text
    robots_path = os.path.join(str(tmp_path), "robots.txt")
    assert os.path.exists(robots_path)
    with open(robots_path, "r", encoding="utf-8") as rf:
        assert "Disallow: /" in rf.read()


def test_generate_dashboard_html_xss_protection(tmp_path):
    out_html = str(tmp_path / "xss.html")
    signals = [
        {
            "ticker": "<script>alert('xss')</script>",
            "name": "<img src=x onerror=alert(1)>",
            "market": "us",
            "is_fund": False,
            "date": "2026-10-10",
            "close": 100.0,
            "currency": "$",
            "position": "long",
            "entry_ref": 90.0,
            "exit_ref": 95.0,
            "distance_pct": 5.0,
            "action": "HOLD_LONG"
        }
    ]
    generate_dashboard_html(signals, [], output_path=out_html)
    with open(out_html, "r", encoding="utf-8") as f:
        html_text = f.read()

    assert "<script>alert('xss')</script>" not in html_text
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_text or "&lt;script&gt;" in html_text


def test_generate_dashboard_html_empty_data(tmp_path):
    out_html = str(tmp_path / "empty.html")
    generate_dashboard_html([], [], output_path=out_html)
    assert os.path.exists(out_html)
    with open(out_html, "r", encoding="utf-8") as f:
        html_text = f.read()
    assert "SuperTrend AI" in html_text
