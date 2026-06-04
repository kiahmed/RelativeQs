from typing import List
import numpy as np
import pandas as pd

def rolling_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    roll_mean = series.rolling(window).mean()
    roll_std = series.rolling(window).std()
    return (series - roll_mean) / roll_std

def rolling_percentile(series: pd.Series, window: int = 20) -> pd.Series:
    # raw=True passes a numpy array so x[-1] is positional; with raw=False pandas 2.x
    # treats x[-1] as a label lookup on the DatetimeIndex and raises KeyError
    return series.rolling(window).apply(lambda x: (x[-1] <= x).mean(), raw=True)

def rolling_correlation(series_a: pd.Series, series_b: pd.Series, window: int = 20) -> pd.Series:
    aligned = pd.concat([series_a, series_b], axis=1).dropna()
    if aligned.shape[0] < window:
        return pd.Series([], dtype=float)
    return aligned.iloc[:,0].pct_change().rolling(window).corr(aligned.iloc[:,1].pct_change())

def normalize_to_prob(x: float) -> float:
    return float(np.tanh(x))
