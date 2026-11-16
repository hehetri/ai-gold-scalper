import math

import pandas as pd
import pytest

from ai_gold_scalper.indicators import atr, ema, rsi, validate_ohlc


def ohlc(rows, index=None):
    return pd.DataFrame(
        rows, columns=["open", "high", "low", "close"],
        index=index if index is not None
        else pd.date_range("2026-01-01", periods=len(rows), freq="min"),
    )


def test_ema_requires_positive_period():
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, 2.0]), 0)


def test_ema_has_warmup_and_does_not_look_ahead():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    full = ema(series, 3)
    assert full.iloc[:2].isna().all()
    assert ema(series.iloc[:4], 3).iloc[-1] == full.iloc[3]


def test_rsi_extremes():
    assert rsi(pd.Series(range(1, 30), dtype=float), 14).iloc[-1] == 100.0
    assert rsi(pd.Series(range(30, 1, -1), dtype=float), 14).iloc[-1] == 0.0


def test_atr_constant_range():
    frame = ohlc([(100, 101, 99, 100)] * 20)
    assert atr(frame, 14).iloc[-1] == pytest.approx(2.0)
    assert atr(frame, 14).iloc[:13].isna().all()


def test_ohlc_requires_columns():
    with pytest.raises(ValueError):
        validate_ohlc(pd.DataFrame({"close": [1.0]}))


def test_ohlc_rejects_duplicate_timestamps():
    idx = pd.to_datetime(["2026-01-01", "2026-01-01"])
    with pytest.raises(ValueError):
        validate_ohlc(ohlc([(1, 2, 0, 1), (1, 2, 0, 1)], index=idx))


@pytest.mark.parametrize("row", [(1, math.nan, 0, 1), (1, 0.5, 0, 1), (1, 2, 1.5, 1)])
def test_ohlc_rejects_non_finite_or_inconsistent_bars(row):
    with pytest.raises(ValueError):
        validate_ohlc(ohlc([row]))
