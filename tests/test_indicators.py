import pandas as pd
import pytest
from ai_gold_scalper.indicators import ema, validate_ohlc


def test_ema_requires_positive_period():
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, 2.0]), 0)


def test_ohlc_requires_columns():
    with pytest.raises(ValueError):
        validate_ohlc(pd.DataFrame({"close": [1.0]}))


def test_ohlc_rejects_duplicate_timestamps():
    idx = pd.to_datetime(["2026-01-01", "2026-01-01"])
    frame = pd.DataFrame({"open":[1,1],"high":[2,2],"low":[0,0],"close":[1,1]}, index=idx)
    with pytest.raises(ValueError):
        validate_ohlc(frame)
