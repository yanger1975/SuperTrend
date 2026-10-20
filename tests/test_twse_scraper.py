import os
import json
import pytest
import pandas as pd
from src.scrapers.twse_scraper import TwseScraper
from src.data_loader import DataLoader

def test_must_have_tw_config():
    path = "data/must_have_tw.json"
    assert os.path.exists(path), f"設定檔 {path} 不存在"
    with open(path, "r", encoding="utf-8") as f:
        tickers = json.load(f)
    assert isinstance(tickers, list)
    assert "0050.TW" in tickers
    assert "00935.TW" in tickers

def test_resolve_ticker_and_date():
    scraper = TwseScraper()
    code, symbol = scraper.resolve_ticker("0050.TW")
    assert code == "0050"
    assert symbol == "0050.TW"

    code2, symbol2 = scraper.resolve_ticker("00935")
    assert code2 == "00935"
    assert symbol2 == "00935.TW"

    assert scraper.to_ad_date("113/10/30") == "2024-10-30"
    assert scraper.to_ad_date("1151008") == "2026-10-08"

def test_parse_stock_day_json():
    scraper = TwseScraper()
    raw_json = {
        "stat": "OK",
        "data": [
            ["113/10/29", "10,000,000", "1,900,000,000", "190.00", "192.00", "189.50", "191.00", "+1.00", "5,000"],
            ["113/10/30", "14,531,256", "2,800,185,309", "192.95", "194.05", "191.50", "191.80", "+0.80", "15,214"]
        ]
    }
    df = scraper.parse_stock_day_json(raw_json)
    assert len(df) == 2
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.iloc[1]["Close"] == 191.80
    assert df.iloc[1]["Volume"] == 14531256.0
    assert str(df.index[1].date()) == "2024-10-30"

def test_twse_prices_json_roundtrip(tmp_path):
    db_file = str(tmp_path / "test_market_data.db")
    json_file = str(tmp_path / "test_twse_prices.json")
    scraper = TwseScraper(db_path=db_file, json_path=json_file)

    dates = pd.date_range("2024-10-01", periods=5, freq="D")
    df = pd.DataFrame({
        "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "High": [102.0, 103.0, 104.0, 105.0, 106.0],
        "Low": [99.0, 100.0, 101.0, 102.0, 103.0],
        "Close": [101.0, 102.0, 103.0, 104.0, 105.0],
        "Volume": [1000.0, 2000.0, 1500.0, 3000.0, 2500.0]
    }, index=dates)

    scraper.storage.upsert_prices(df, "0050.TW", "1d")
    scraper.storage.upsert_ticker_info("0050.TW", "元大台灣50", "etf", "twse")

    ok = scraper.export_prices_to_json(json_path=json_file)
    assert ok is True
    assert os.path.exists(json_file)

    empty_db = str(tmp_path / "empty_market_data.db")
    new_scraper = TwseScraper(db_path=empty_db, json_path=json_file)
    imported_count = new_scraper.import_prices_from_json(json_path=json_file)
    assert imported_count == 5

    restored_df = new_scraper.storage.query_prices("0050.TW", "1d", "2024-10-01", "2024-10-05")
    assert len(restored_df) == 5
    assert restored_df.iloc[0]["Close"] == 101.0

    info = new_scraper.storage.get_ticker_info("0050.TW")
    assert info is not None
    assert info["name"] == "元大台灣50"

def test_parse_daily_snapshot():
    scraper = TwseScraper()
    raw_snapshot = [
        {
            "Code": "0050",
            "Name": "元大台灣50",
            "OpeningPrice": "192.50",
            "HighestPrice": "193.00",
            "LowestPrice": "191.00",
            "ClosingPrice": "192.00",
            "TradeVolume": "12000000"
        },
        {
            "Code": "00935",
            "Name": "野村臺灣新科技50",
            "OpeningPrice": "22.00",
            "HighestPrice": "22.50",
            "LowestPrice": "21.80",
            "ClosingPrice": "22.30",
            "TradeVolume": "3000000"
        }
    ]
    parsed = scraper.parse_daily_snapshot(raw_snapshot)
    assert "0050" in parsed
    assert parsed["0050"]["Close"] == 192.00
    assert parsed["0050"]["Name"] == "元大台灣50"
    assert "00935" in parsed
    assert parsed["00935"]["Close"] == 22.30

def test_data_loader_twse_routing(tmp_path):
    db_file = str(tmp_path / "test_market_data.db")
    loader = DataLoader(db_path=db_file)

    # 預先存入測試資料
    dates = pd.date_range("2024-10-01", periods=10, freq="D")
    sample_df = pd.DataFrame({
        "Open": [100.0] * 10,
        "High": [105.0] * 10,
        "Low": [95.0] * 10,
        "Close": [102.0] * 10,
        "Volume": [50000.0] * 10
    }, index=dates)
    loader.storage.upsert_prices(sample_df, ticker="0050.TW", interval="1d")
    loader.storage.upsert_ticker_info("0050.TW", "元大台灣50", "etf", "twse")

    df = loader.fetch_data("0050.TW", start_date="2024-10-01", end_date="2024-10-10")
    assert not df.empty
    assert len(df) == 10
    assert "Close" in df.columns

def test_get_latest_snapshot_bar_and_fetch_recent_days():
    scraper = TwseScraper()
    scraper._daily_snapshot_cache = {
        "0050": {
            "Code": "0050",
            "Name": "元大台灣50",
            "Open": 192.5,
            "High": 193.0,
            "Low": 191.0,
            "Close": 192.0,
            "Volume": 12000000.0,
            "Date": "2026-10-16"
        }
    }
    scraper._daily_snapshot_time = 9999999999.0

    bar = scraper.get_latest_snapshot_bar("0050.TW")
    assert bar is not None
    assert len(bar) == 1
    assert bar.iloc[0]["Close"] == 192.0
    assert str(bar.index[0].date()) == "2026-10-16"

    # 測試 fetch_recent_days 當起始日就是 snapshot 日期時直接命中快照
    recent = scraper.fetch_recent_days("0050.TW", "2026-10-16", "2026-10-16")
    assert len(recent) == 1
    assert recent.iloc[0]["Close"] == 192.0

def test_fetch_realtime_quotes_and_bar(monkeypatch):
    scraper = TwseScraper()
    mock_mis_response = {
        "msgArray": [
            {
                "c": "0050",
                "n": "元大台灣50",
                "d": "20261020",
                "t": "12:10:00",
                "o": "107.6500",
                "h": "108.3000",
                "l": "107.3000",
                "z": "107.8000",
                "pz": "107.7500",
                "y": "108.1500",
                "b": "107.8000_107.7500_",
                "a": "107.8500_107.9000_",
                "v": "56000"
            },
            {
                "c": "00935",
                "n": "野村臺灣新科技50",
                "d": "20261020",
                "t": "12:10:05",
                "o": "56.2000",
                "h": "56.8500",
                "l": "56.0500",
                "z": "-",
                "pz": "-",
                "y": "56.5000",
                "b": "56.2500_56.2000_",
                "a": "56.3500_56.4000_",
                "v": "5700"
            }
        ]
    }

    class MockResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def read(self):
            return json.dumps(mock_mis_response).encode("utf-8")

    def mock_urlopen(req, timeout=15):
        return MockResponse()

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    quotes = scraper.fetch_realtime_quotes(["0050.TW", "00935.TW"])
    assert "0050.TW" in quotes
    assert "00935.TW" in quotes

    q0050 = quotes["0050.TW"]
    assert q0050["close"] == 107.80
    assert q0050["open"] == 107.65
    assert q0050["high"] == 108.30
    assert q0050["low"] == 107.30
    assert q0050["date"] == "2026-10-20"

    # 00935 z 是 "-"，應取 (56.25 + 56.35) / 2 = 56.30
    q00935 = quotes["00935.TW"]
    assert q00935["close"] == 56.30

    bar = scraper.get_realtime_bar("0050.TW")
    assert bar is not None
    assert len(bar) == 1
    assert bar.iloc[0]["Close"] == 107.80
    assert list(bar.columns) == ["Open", "High", "Low", "Close", "Volume"]

