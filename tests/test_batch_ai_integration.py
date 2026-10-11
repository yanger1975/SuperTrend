# -*- coding: utf-8 -*-
import os
import pytest
from run_batch_optimization_supertrend_ai import build_telegram_blocks_ai

def test_telegram_blocks_contain_dashboard_link():
    mock_results = [{
        "ticker": "SPY",
        "display_name": "SPY",
        "is_fund": False,
        "pos_value": "long",
        "distance_pct": 1.0,
        "raw": {
            "latest_signal": {
                "date": "2026-10-10",
                "close": "580",
                "entry_ref": "570",
                "exit_ref": "575"
            }
        }
    }]
    test_url = "https://yanger1975.github.io/SuperTrend/"
    blocks = build_telegram_blocks_ai(
        mock_results,
        is_saturday=False,
        market_type="us",
        dashboard_url=test_url
    )
    joined = "\n".join(blocks)
    assert test_url in joined
    assert "儀表板" in joined or "Dashboard" in joined


def test_telegram_blocks_read_env_dashboard_link(monkeypatch):
    mock_results = [{
        "ticker": "0050.TW",
        "display_name": "元大台灣50",
        "is_fund": False,
        "pos_value": "long",
        "distance_pct": 2.0,
        "raw": {
            "latest_signal": {
                "date": "2026-10-11",
                "close": "195",
                "entry_ref": "188",
                "exit_ref": "190"
            }
        }
    }]
    env_url = "https://custom.github.io/dashboard/"
    monkeypatch.setenv("GITHUB_PAGES_URL", env_url)
    blocks = build_telegram_blocks_ai(
        mock_results,
        is_saturday=False,
        market_type="tw"
    )
    joined = "\n".join(blocks)
    assert env_url in joined
