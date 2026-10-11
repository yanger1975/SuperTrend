import os
import json
import pytest
from run_batch_optimization_supertrend_ai import export_latest_signals_to_json, load_latest_signals_from_json

def test_export_and_load_latest_signals(tmp_path):
    test_file = str(tmp_path / "data" / "latest_signals_ai.json")
    mock_results = [
        {
            "ticker": "0050.TW",
            "display_name": "元大台灣50",
            "is_fund": False,
            "pos_value": "long",
            "distance_pct": 2.5,
            "raw": {
                "latest_signal": {
                    "date": "2026-10-11",
                    "close": 195.5,
                    "entry_ref": 188.0,
                    "exit_ref": 190.0,
                    "action": "HOLD_LONG"
                }
            }
        },
        {
            "ticker": "SPY",
            "display_name": "SPY",
            "is_fund": False,
            "pos_value": "cash",
            "distance_pct": -1.2,
            "raw": {
                "latest_signal": {
                    "date": "2026-10-10",
                    "close": 580.0,
                    "entry_ref": 585.0,
                    "exit_ref": "-",
                    "action": "WAIT_CASH"
                }
            }
        }
    ]

    out_path = export_latest_signals_to_json(mock_results, output_path=test_file)
    assert os.path.exists(out_path)

    loaded = load_latest_signals_from_json(test_file)
    assert len(loaded) == 2

    # Verify 0050.TW
    assert loaded[0]["ticker"] == "0050.TW"
    assert loaded[0]["name"] == "元大台灣50"
    assert loaded[0]["market"] == "tw"
    assert loaded[0]["currency"] == "NT$"
    assert loaded[0]["position"] == "long"
    assert loaded[0]["distance_pct"] == 2.5
    assert loaded[0]["entry_ref"] == 188.0
    assert loaded[0]["exit_ref"] == 190.0
    assert loaded[0]["action"] == "HOLD_LONG"

    # Verify SPY
    assert loaded[1]["ticker"] == "SPY"
    assert loaded[1]["market"] == "us"
    assert loaded[1]["currency"] == "$"
    assert loaded[1]["position"] == "cash"
    assert loaded[1]["distance_pct"] == -1.2


def test_export_empty_results(tmp_path):
    test_file = str(tmp_path / "latest_signals_empty.json")
    out_path = export_latest_signals_to_json([], output_path=test_file)
    assert os.path.exists(out_path)
    loaded = load_latest_signals_from_json(test_file)
    assert loaded == []


def test_load_nonexistent_file():
    loaded = load_latest_signals_from_json("nonexistent/path/signals.json")
    assert loaded == []
