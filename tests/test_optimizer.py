import pandas as pd
import pytest
from src.optimizer import ParameterOptimizer

def test_optimizer_train_test_split():
    # 建立虛擬 OHLCV 資料 (20 筆)
    idx = pd.date_range(start="2023-01-01", periods=20, freq="D")
    df = pd.DataFrame({
        "Open": [100.0] * 20,
        "High": [105.0] * 20,
        "Low": [95.0] * 20,
        "Close": [101.0, 102.0, 103.0, 98.0, 97.0, 102.0, 104.0, 105.0, 102.0, 101.0] * 2,
        "Volume": [1000] * 20
    }, index=idx)

    optimizer = ParameterOptimizer(df)

    # 測試樣本內/樣本外各半 (train_ratio = 0.5)
    train_res, test_res = optimizer.optimize(
        st_periods=[3],
        st_multipliers=[2.0],
        ma_periods=[5],
        target_metric="Custom Score",
        train_ratio=0.5
    )

    assert not train_res.empty
    assert not test_res.empty
    assert "Custom Score" in train_res.columns
    # 確認優化結果已成功依照得分進行降序排序
    if len(train_res) > 1:
        assert train_res["Custom Score"].iloc[0] >= train_res["Custom Score"].iloc[1]
