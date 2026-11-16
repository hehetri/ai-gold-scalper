import pandas as pd

from ai_gold_scalper.strategy import Direction, m1_trigger, m5_bias


def bars(values):
    idx = pd.date_range("2026-01-01", periods=len(values), freq="min")
    return pd.DataFrame(
        {
            "open": [v - 0.1 for v in values],
            "high": [v + 0.3 for v in values],
            "low": [v - 0.3 for v in values],
            "close": values,
        },
        index=idx,
    )


def test_short_history_has_no_bias():
    assert m5_bias(bars([100, 101, 102])) is Direction.FLAT


def test_flat_bias_never_triggers():
    assert not m1_trigger(bars([float(v) for v in range(100, 130)]), Direction.FLAT)


def test_trending_series_gives_directional_bias():
    up = [2000 + 0.5 * i for i in range(260)]
    assert m5_bias(bars(up)) is Direction.LONG
    assert m5_bias(bars(up[::-1])) is Direction.SHORT


def test_long_trigger_after_pullback_below_fast_ema():
    values = [2000 + 0.5 * i for i in range(258)]
    values += [values[-1] - 6.0, values[-1] + 1.0]  # dip under EMA9, then bullish reclaim
    frame = bars(values)
    assert m1_trigger(frame, Direction.LONG)
    assert not m1_trigger(frame, Direction.SHORT)
    assert not m1_trigger(frame.iloc[:-1], Direction.LONG)  # no trigger on the dip bar itself
