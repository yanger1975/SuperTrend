import os
import pytest
import pandas as pd
from src.storage import SQLiteStorage
from src.scrapers.ezmoney_scraper import EzMoneyScraper
from src.data_loader import DataLoader


def test_ticker_info_schema_and_upsert(tmp_path):
    db_file = str(tmp_path / "test_market_data.db")
    storage = SQLiteStorage(db_path=db_file)

    # 寫入 ticker_info
    storage.upsert_ticker_info(
        ticker="33YTW.EZ",
        name="統一全球新科技基金",
        asset_type="fund",
        source="ezmoney"
    )

    # 讀取 ticker_info
    info = storage.get_ticker_info("33YTW.EZ")
    assert info is not None
    assert info["ticker"] == "33YTW.EZ"
    assert info["name"] == "統一全球新科技基金"
    assert info["asset_type"] == "fund"
    assert info["source"] == "ezmoney"


def test_date_conversion_helpers(tmp_path):
    db_file = str(tmp_path / "test_market_data.db")
    scraper = EzMoneyScraper(db_path=db_file)

    roc_date = scraper.to_roc_date("2025-01-02")
    assert roc_date == "114/01/02"

    ad_date = scraper.to_ad_date("114/01/02")
    assert ad_date == "2025-01-02"


def test_symbol_code_resolution(tmp_path):
    db_file = str(tmp_path / "test_market_data.db")
    scraper = EzMoneyScraper(db_path=db_file)

    code, name, symbol = scraper.resolve_symbol("33YTW.EZ")
    assert code == "33YTW"
    assert name == "統一全球新科技基金"
    assert symbol == "33YTW.EZ"

    code2, name2, symbol2 = scraper.resolve_symbol("統一全球新科技基金")
    assert code2 == "33YTW"
    assert name2 == "統一全球新科技基金"
    assert symbol2 == "33YTW.EZ"


def test_data_loader_preserves_zero_open_high_low():
    loader = DataLoader()
    raw_df = pd.DataFrame({
        "Open": [0.0, 0.0],
        "High": [0.0, 0.0],
        "Low": [0.0, 0.0],
        "Close": [117.15, 117.60],
        "Volume": [0.0, 0.0]
    }, index=pd.to_datetime(["2026-07-22", "2026-07-23"]))

    cleaned = loader.validate_and_clean_data(raw_df)
    assert not cleaned.empty
    assert (cleaned["Open"] == 0.0).all()
    assert (cleaned["High"] == 0.0).all()
    assert (cleaned["Low"] == 0.0).all()
    assert (cleaned["Close"] > 0).all()
