from src.data_loader import DataLoader
from src.indicators import compute_hma, compute_supertrend


def test_ezmoney_fund_fetch_and_indicators():
    loader = DataLoader()
    # 抓取 統一全球新科技基金 (33YTW.EZ)
    df = loader.fetch_data("33YTW.EZ", start_date="2024-01-01", end_date="2026-07-24")

    assert not df.empty
    assert "Close" in df.columns
    assert len(df) > 50

    # 驗證元數據已建立
    info = loader.storage.get_ticker_info("33YTW.EZ")
    assert info is not None
    assert info["name"] == "統一全球新科技基金"
    assert info["asset_type"] == "fund"

    # 驗證基金收盤價 (淨值) 與技術指標運算相容性
    hma_series = compute_hma(df["Close"], period=20)
    assert not hma_series.dropna().empty

    st_df, trend_series = compute_supertrend(df, period=10, multiplier=3.0)
    assert "SuperTrend" in st_df.columns
    assert "Trend" in st_df.columns


