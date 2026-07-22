import pandas as pd
import numpy as np

def compute_hma(series: pd.Series, period: int) -> pd.Series:
    """
    計算 Hull Moving Average (HMA)
    藉由加權移動平均 (WMA) 降低延遲，並保持平滑度。
    """
    if len(series) < period:
        return pd.Series(np.nan, index=series.index, dtype=float)

    def wma(s: pd.Series, p: int) -> pd.Series:
        weights = np.arange(1, p + 1)
        return s.rolling(p).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))

    # Raw HMA = 2 * WMA(n/2) - WMA(n)
    raw_hma = 2 * wma(series, half_period) - wma(series, period)
    # HMA = WMA(Raw HMA, sqrt(n))
    return wma(raw_hma, sqrt_period)

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    計算相對強弱指標 (RSI)
    使用與 TradingView 及 Wilder 相同的 RMA (Running Moving Average) 進行平滑。
    """
    if len(series) < period:
        return pd.Series(np.nan, index=series.index, dtype=float)

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's RMA = ewm(alpha=1/period, adjust=False)
    avg_gain = gain.ewm(alpha=1.0/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    # 將前 period 個值設為 NaN，與標準技術分析一致
    rsi.iloc[:period] = np.nan
    return rsi

def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    計算平均趨向指標 (ADX)
    用於判斷趨勢強度，防範在盤整期中交易。
    """
    if len(df) < period * 2:
        return pd.Series(np.nan, index=df.index, dtype=float)

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # 1. 計算 True Range (TR)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    # 2. 計算 DM+ 和 DM-
    up_move = high.diff()
    down_move = low.shift() - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # 3. 使用 Wilder's RMA 平滑 TR, DM+, DM-
    atr = tr.ewm(alpha=1.0/period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1.0/period, adjust=False).mean() / (atr + 1e-10)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1.0/period, adjust=False).mean() / (atr + 1e-10)

    # 4. 計算 DX 與 ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(alpha=1.0/period, adjust=False).mean()

    adx.iloc[:period * 2] = np.nan
    return adx

def compute_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> (pd.DataFrame, pd.Series):
    """
    計算 SuperTrend 指標。
    回傳：
        1. 帶有 'SuperTrend' 與 'Trend' 欄位的 DataFrame。
        2. Trend 數值 Series (1 代表多頭，-1 代表空頭)。
    """
    if len(df) < period:
        res = df.copy()
        res["SuperTrend"] = np.nan
        res["Trend"] = 1
        return res, res["Trend"]

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # 1. 計算 True Range 與 ATR
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    # 標準 SuperTrend 通常使用 RMA 平滑的 ATR
    atr = tr.ewm(alpha=1.0/period, adjust=False).mean()

    # 2. 計算基礎上下軌
    hl2 = (high + low) / 2
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)

    # 3. 迭代計算最終上下軌與趨勢方向
    final_ub = np.zeros(len(df))
    final_lb = np.zeros(len(df))
    trend = np.ones(len(df), dtype=int)
    supertrend = np.zeros(len(df))

    # 初始化第一筆資料
    final_ub[0] = basic_ub.iloc[0]
    final_lb[0] = basic_lb.iloc[0]
    # 預設第一筆為多頭趨勢
    trend[0] = 1
    supertrend[0] = final_lb[0]

    for i in range(1, len(df)):
        # Upper Band
        if basic_ub.iloc[i] < final_ub[i-1] or close.iloc[i-1] > final_ub[i-1]:
            final_ub[i] = basic_ub.iloc[i]
        else:
            final_ub[i] = final_ub[i-1]

        # Lower Band
        if basic_lb.iloc[i] > final_lb[i-1] or close.iloc[i-1] < final_lb[i-1]:
            final_lb[i] = basic_lb.iloc[i]
        else:
            final_lb[i] = final_lb[i-1]

        # Trend
        if close.iloc[i] > final_ub[i]:
            trend[i] = 1
        elif close.iloc[i] < final_lb[i]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]

        # SuperTrend Value
        if trend[i] == 1:
            supertrend[i] = final_lb[i]
        else:
            supertrend[i] = final_ub[i]

    result_df = df.copy()
    result_df["SuperTrend"] = supertrend
    result_df["Trend"] = pd.Series(trend, index=df.index)
    return result_df, result_df["Trend"]
