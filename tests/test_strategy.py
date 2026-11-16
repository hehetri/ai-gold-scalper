import pandas as pd
from ai_gold_scalper.strategy import Direction, m5_bias, m1_trigger


def bars(values):
    idx = pd.date_range("2026-01-01", periods=len(values), freq="min")
    return pd.DataFrame({"open":[v-0.1 for v in values],"high":[v+0.3 for v in values],"low":[v-0.3 for v in values],"close":values}, index=idx)


def test_short_history_has_no_bias():
    assert m5_bias(bars([100,101,102])) is Direction.FLAT


def test_flat_bias_never_triggers():
    assert not m1_trigger(bars(list(range(100,130))), Direction.FLAT)
