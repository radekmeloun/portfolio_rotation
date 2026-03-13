# tests/conftest.py
from datetime import datetime
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def bdays():
    return pd.bdate_range(start="2023-01-01", end="2024-12-31", freq="B")


@pytest.fixture
def price_df_factory():
    def _make(prices: dict[str, list[float] | np.ndarray], index=None):
        if index is None:
            n = len(next(iter(prices.values())))
            index = pd.bdate_range(end=datetime.now(), periods=n, freq="B")
        return pd.DataFrame(prices, index=index)
    return _make
