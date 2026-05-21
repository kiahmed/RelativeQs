from typing import List
import numpy as np
import pandas as pd

def rolling_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    roll_mean = series.rolling(window).mean()
    roll_std = series.rolling(window).std()
    return (series - roll_mean) / roll_std

def rolling_percentile(series: pd.Series, window: int = 20) -> pd.Series:
    return series.rolling(window).apply(lambda x: (x[-1] <= x).mean(), raw=False)

def rolling_correlation(series_a: pd.Series, series_b: pd.Series, window: int = 20) -> pd.Series:
    aligned = pd.concat([series_a, series_b], axis=1).dropna()
    if aligned.shape[0] < window:
        return pd.Series([], dtype=float)
    return aligned.iloc[:,0].pct_change().rolling(window).corr(aligned.iloc[:,1].pct_change())

def normalize_to_prob(x: float) -> float:
    return float(np.tanh(x))
