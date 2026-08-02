import pandas as pd
import numpy as np
from src.supertrend_ai.kmeans import kmeans_1d_labels
from tqdm.auto import tqdm
def calculate_atr(high, low, close, length):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Using Wilder's Smoothing for ATR (RMA)
    atr = tr.ewm(alpha=1/length, adjust=False).mean()
    return atr

def compute_supertrend_core(high, low, close, atr, factor):
    n = len(close)
    upper = np.zeros(n)
    lower = np.zeros(n)
    trend = np.ones(n)
    output = np.zeros(n)
    
    hl2 = (high + low) / 2
    
    up_arr = hl2 + atr * factor
    dn_arr = hl2 - atr * factor
    
    close_vals = close.values
    up_vals = up_arr.values
    dn_vals = dn_arr.values
    
    upper[0] = up_vals[0]
    lower[0] = dn_vals[0]
    trend[0] = 1
    output[0] = lower[0]
    
    for i in range(1, n):
        if np.isnan(close_vals[i]) or np.isnan(atr.iloc[i]):
            upper[i] = np.nan
            lower[i] = np.nan
            trend[i] = trend[i-1]
            output[i] = np.nan
            continue
            
        up = up_vals[i]
        dn = dn_vals[i]
        
        # Upper band
        if close_vals[i-1] < upper[i-1] and not np.isnan(upper[i-1]):
            upper[i] = min(up, upper[i-1])
        else:
            upper[i] = up
            
        # Lower band
        if close_vals[i-1] > lower[i-1] and not np.isnan(lower[i-1]):
            lower[i] = max(dn, lower[i-1])
        else:
            lower[i] = dn
            
        # Trend
        if close_vals[i] > upper[i]:
            trend[i] = 1
        elif close_vals[i] < lower[i]:
            trend[i] = 0
        else:
            trend[i] = trend[i-1]
            
        # Output
        if trend[i] == 1:
            output[i] = lower[i]
        else:
            output[i] = upper[i]
            
    return pd.Series(output, index=close.index)

def supertrend_ai(df, length=10, min_mult=1.0, max_mult=5.0, step=0.5, perf_alpha: float = 10.0,
    from_cluster: str = 'Best',
    update_freq: int = 1,
    show_progress: bool = False
) -> pd.DataFrame:
    """
    SuperTrend AI (Clustering) logic.
    Returns the dataframe with SuperTrend_AI, SuperTrend_AI_Direction, Target_Factor.
    """
    if not {'High', 'Low', 'Close'}.issubset(df.columns):
        raise ValueError("DataFrame must contain 'High', 'Low', 'Close' columns")
    if length <= 0:
        raise ValueError("length must be > 0")
    if min_mult > max_mult:
        raise ValueError("min_mult must be <= max_mult")
    if step <= 0:
        raise ValueError("step must be > 0")
    if perf_alpha <= 0:
        raise ValueError("perf_alpha must be > 0")
    if update_freq <= 0:
        raise ValueError("update_freq must be > 0")
    if from_cluster not in {'Best', 'Average', 'Worst'}:
        raise ValueError("from_cluster must be one of 'Best', 'Average', 'Worst'")
        
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    n_factors = int(round((max_mult - min_mult) / step)) + 1
    factors = np.linspace(min_mult, max_mult, n_factors)
    atr = calculate_atr(high, low, close, length)
    
    # 1. Compute basic supertrends and their outputs
    spt_outputs = {}
    for f in factors:
        spt_outputs[f] = compute_supertrend_core(high, low, close, atr, f)
        
    # 2. Compute performances
    perfs = {}
    close_diff = (close - close.shift(1)).fillna(0)
    for f in factors:
        out = spt_outputs[f]
        diff = np.sign(close.shift(1) - out.shift(1)).fillna(0)
        raw_perf = close_diff * diff
        perf = raw_perf.ewm(alpha=2/(perf_alpha+1), adjust=False).mean()
        perfs[f] = perf
        
    perf_df = pd.DataFrame(perfs)
    target_factors = np.full(len(df), np.nan)
    
    # 3. K-Means Clustering
    n = len(df)
    n = len(df)
    
    perf_vals = perf_df.values
    
    
    target_factors[0] = float(np.mean(factors))
    
    iterator = range(n)
    if show_progress:
        iterator = tqdm(iterator, desc="SuperTrend AI 逐 K 線聚類運算", leave=False)
        
    for i in iterator:
        if i == 0:
            continue
            
        row_perf = perf_vals[i]
        if np.isnan(row_perf).any():
            continue
            
        if len(factors) == 0:
            row_perf = perf_vals[i]
        mask_valid = ~np.isnan(row_perf)
        if not mask_valid.any():
            if i > 0 and not np.isnan(target_factors[i-1]):
                target_factors[i] = target_factors[i-1]
            continue
            
        if update_freq > 1 and i % update_freq != 0 and i > 0:
            last_valid = target_factors[:i][~np.isnan(target_factors[:i])]
            if len(last_valid) > 0:
                target_factors[i] = last_valid[-1]
            continue
            
        data = row_perf[mask_valid]
        n_clusters = min(3, len(factors))
        
        centers, labels = kmeans_1d_labels(data, k=n_clusters)
        
        sorted_indices = np.argsort(centers) 
        
        if n_clusters == 3:
            if from_cluster == 'Best':
                from_idx = -1
            elif from_cluster == 'Worst':
                from_idx = 0
            else:
                from_idx = 1
        elif n_clusters == 2:
            if from_cluster == 'Best':
                from_idx = -1
            elif from_cluster == 'Average' or from_cluster == 'Worst':
                from_idx = 0
        else:
            from_idx = 0
            
        target_original_label = sorted_indices[from_idx]
        mask = (labels == target_original_label)
        target_f = np.mean(factors[mask_valid][mask]) if np.any(mask) else np.mean(factors)
        
        target_factors[i] = target_f
        
    # 4. Compute Adaptive SuperTrend
    hl2 = (high + low) / 2
    upper = np.zeros(n)
    lower = np.zeros(n)
    trend = np.ones(n)
    ts = np.zeros(n)
    
    close_vals = close.values
    atr_vals = atr.values
    hl2_vals = hl2.values
    
    for i in range(n):
        if np.isnan(target_factors[i]) or np.isnan(close_vals[i]) or np.isnan(atr_vals[i]):
            upper[i] = np.nan
            lower[i] = np.nan
            if i > 0:
                trend[i] = trend[i-1]
            ts[i] = np.nan
            continue
            
        if i == 0 or np.isnan(upper[i-1]):
            upper[i] = hl2_vals[i] + atr_vals[i] * target_factors[i]
            lower[i] = hl2_vals[i] - atr_vals[i] * target_factors[i]
            ts[i] = lower[i]
            continue
            
        up = hl2_vals[i] + atr_vals[i] * target_factors[i]
        dn = hl2_vals[i] - atr_vals[i] * target_factors[i]
        
        if close_vals[i-1] < upper[i-1]:
            upper[i] = min(up, upper[i-1])
        else:
            upper[i] = up
            
        if close_vals[i-1] > lower[i-1]:
            lower[i] = max(dn, lower[i-1])
        else:
            lower[i] = dn
            
        if close_vals[i] > upper[i]:
            trend[i] = 1
        elif close_vals[i] < lower[i]:
            trend[i] = 0
        else:
            trend[i] = trend[i-1]
            
        if trend[i] == 1:
            ts[i] = lower[i]
        else:
            ts[i] = upper[i]
            
    df_out = df.copy()
    df_out['SuperTrend_AI'] = pd.Series(ts, index=df.index)
    df_out['SuperTrend_AI_Direction'] = pd.Series(trend, index=df.index, dtype=int)
    df_out['Target_Factor'] = pd.Series(target_factors, index=df.index)
    return df_out
