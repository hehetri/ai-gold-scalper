"""M5 context / M1 trigger baseline. This module never sends orders."""
from enum import Enum
import pandas as pd
from .indicators import ema, validate_ohlc


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


def features(frame: pd.DataFrame, fast: int = 9, slow: int = 21, regime: int = 200) -> pd.DataFrame:
    validate_ohlc(frame)
    if not 0 < fast < slow < regime:
        raise ValueError("Require 0 < fast < slow < regime")
    out = frame.copy()
    out["ema_fast"] = ema(out["close"], fast)
    out["ema_slow"] = ema(out["close"], slow)
    out["ema_regime"] = ema(out["close"], regime)
    return out


def m5_bias(m5: pd.DataFrame) -> Direction:
    data = features(m5).dropna()
    if data.empty:
        return Direction.FLAT
    last = data.iloc[-1]  # caller must pass completed bars only
    if last.close > last.ema_regime and last.ema_fast > last.ema_slow:
        return Direction.LONG
    if last.close < last.ema_regime and last.ema_fast < last.ema_slow:
        return Direction.SHORT
    return Direction.FLAT


def m1_trigger(m1: pd.DataFrame, bias: Direction) -> bool:
    if bias is Direction.FLAT:
        return False
    data = features(m1).dropna()
    if len(data) < 2:
        return False
    prev, last = data.iloc[-2], data.iloc[-1]  # completed bars only
    if bias is Direction.LONG:
        return bool(last.close > last.open and last.close > last.ema_fast and prev.close <= prev.ema_fast)
    return bool(last.close < last.open and last.close < last.ema_fast and prev.close >= prev.ema_fast)
