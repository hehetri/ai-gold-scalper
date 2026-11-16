"""Pure indicator functions; input data must be chronological."""
import numpy as np
import pandas as pd


def validate_ohlc(frame: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("OHLC frame is empty")
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("OHLC index must be chronological and unique")
    ohlc = frame[["open", "high", "low", "close"]].astype(float)
    if not np.isfinite(ohlc.to_numpy()).all():
        raise ValueError("OHLC values must be finite (no NaN/inf)")
    if (ohlc["high"] < ohlc[["open", "close", "low"]].max(axis=1)).any() or (
        ohlc["low"] > ohlc[["open", "close"]].min(axis=1)
    ).any():
        raise ValueError("OHLC bars are inconsistent (high/low do not bound open/close)")


def ema(series: pd.Series, period: int) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be positive")
    return series.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be positive")
    delta = series.astype(float).diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.where(loss != 0)
    result = 100 - 100 / (1 + rs)
    result = result.mask((loss == 0) & (gain > 0), 100.0)
    return result.mask((gain == 0) & (loss > 0), 0.0)


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder average true range from completed OHLC bars."""
    if period <= 0:
        raise ValueError("period must be positive")
    validate_ohlc(frame)
    high, low = frame["high"].astype(float), frame["low"].astype(float)
    prev_close = frame["close"].astype(float).shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
