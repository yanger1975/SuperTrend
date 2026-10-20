import pytest
from run_intraday_tw_signals import collect_tw_tickers, build_intraday_telegram_report

def test_collect_tw_tickers(tmp_path, monkeypatch):
    test_json = tmp_path / "must_have_tw.json"
    test_json.write_text('["0050.TW", "00935.TW", "33YTW.EZ", "25YTW.EZ"]', encoding="utf-8")
    monkeypatch.setattr("run_intraday_tw_signals.os.path.exists", lambda path: True if "must_have_tw.json" in path else False)
    
    # Test reading
    tickers = collect_tw_tickers()
    assert "0050.TW" in tickers
    assert "00935.TW" in tickers
    assert "33YTW.EZ" not in tickers  # 基金應被排除

def test_build_intraday_telegram_report_with_flips():
    eval_results = [
        {
            "ticker": "0050.TW",
            "name": "元大台灣50",
            "date": "2026-10-20",
            "time": "13:10:00",
            "close": 115.00,
            "open": 110.00,
            "high": 116.00,
            "low": 109.50,
            "volume": 50000.0,
            "best_bid": 114.95,
            "best_ask": 115.05,
            "curr_pos": "long",
            "prev_pos": "cash",
            "signal_status": "NEW_BUY",
            "status_label": "【🟢 盤中突破買進】",
            "entry_ref": "-",
            "exit_ref": "112.00",
            "st_line": 112.00,
            "distance_pct": 2.68
        },
        {
            "ticker": "00935.TW",
            "name": "野村臺灣新科技50",
            "date": "2026-10-20",
            "time": "13:10:05",
            "close": 55.00,
            "open": 56.50,
            "high": 56.80,
            "low": 54.80,
            "volume": 8000.0,
            "best_bid": 54.95,
            "best_ask": 55.05,
            "curr_pos": "cash",
            "prev_pos": "long",
            "signal_status": "NEW_SELL",
            "status_label": "【🔴 盤中跌破賣出】",
            "entry_ref": "57.50",
            "exit_ref": "-",
            "st_line": 57.50,
            "distance_pct": -4.35
        }
    ]

    blocks = build_intraday_telegram_report(eval_results)
    full_text = "\n".join(blocks)

    assert "SuperTrend AI 台股盤中即時快訊 (13:10)" in full_text
    assert "今日重點行動指示" in full_text
    assert "新進場訊號 (BUY)" in full_text
    assert "新出場訊號 (SELL)" in full_text
    assert "0050.TW" in full_text
    assert "00935.TW" in full_text

def test_build_intraday_telegram_report_no_flips():
    eval_results = [
        {
            "ticker": "0050.TW",
            "name": "元大台灣50",
            "date": "2026-10-20",
            "time": "13:10:00",
            "close": 107.80,
            "open": 107.50,
            "high": 108.30,
            "low": 107.30,
            "volume": 50000.0,
            "best_bid": 107.75,
            "best_ask": 107.80,
            "curr_pos": "cash",
            "prev_pos": "cash",
            "signal_status": "WAIT",
            "status_label": "【空手觀望】",
            "entry_ref": "114.17",
            "exit_ref": "-",
            "st_line": 114.17,
            "distance_pct": -5.58
        }
    ]

    blocks = build_intraday_telegram_report(eval_results)
    full_text = "\n".join(blocks)

    assert "今日盤中無重大轉折訊號" in full_text
    assert "觀望 (Wait)" in full_text
    assert "NT$107.80" in full_text
