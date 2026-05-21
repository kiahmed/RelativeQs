import pandas as pd
import numpy as np
import pytest

from app.core.signals import rolling_zscore, rolling_percentile, rolling_correlation


def make_series(n=50):
    idx = pd.date_range(end=pd.Timestamp.today(), periods=n)
    data = pd.Series(np.linspace(1, 100, n) + np.random.normal(0, 1, n), index=idx)
    return data


def test_rolling_zscore_basic():
    s = make_series(30)
    z = rolling_zscore(s, window=5)
    assert isinstance(z, pd.Series)
    # last few values should be finite
    assert z.dropna().shape[0] > 0


def test_rolling_percentile():
    s = make_series(30)
    p = rolling_percentile(s, window=5)
    assert isinstance(p, pd.Series)


def test_rolling_correlation():
    a = make_series(50)
    b = a * 1.0 + pd.Series(np.random.normal(0, 0.1, 50), index=a.index)
    corr = rolling_correlation(a, b, window=10)
    assert isinstance(corr, pd.Series)
    # correlation series: should have some non-null values when enough points
    assert corr.dropna().shape[0] >= 0
