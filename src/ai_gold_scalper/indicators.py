"""Pure indicator functions; input data must be chronological."""
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
