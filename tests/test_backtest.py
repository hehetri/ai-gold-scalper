import pandas as pd
import pytest

from ai_gold_scalper.backtest import run_backtest


def test_backtest_uses_stop_first_when_both_levels_hit():
    bars = pd.DataFrame(
        {"open": [100, 100, 100], "high": [100, 103, 100],
         "low": [100, 97, 100], "close": [100, 100, 100]},
        index=pd.date_range("2026-01-01", periods=3, freq="min"),
    )
    result = run_backtest(
        bars, lambda history, i: "long" if i == 1 else None,
        stop_distance=1, reward_risk=2,
    )
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop"
    assert result.net_profit == pytest.approx(-1)


def test_empty_signal_returns_no_trades():
    bars = pd.DataFrame(
        {"open": [100, 100], "high": [101, 101], "low": [99, 99], "close": [100, 100]},
        index=pd.date_range("2026-01-01", periods=2, freq="min"),
    )
    result = run_backtest(bars, lambda history, i: None, stop_distance=1)
    assert result.trades == ()
    assert result.net_profit == 0
