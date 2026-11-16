import math

import pandas as pd
import pytest

from ai_gold_scalper.backtest import run_backtest


def frame(rows):
    """rows: (open, high, low, close)."""
    return pd.DataFrame(
        rows, columns=["open", "high", "low", "close"],
        index=pd.date_range("2026-01-01", periods=len(rows), freq="min"),
    )


def once(side, at=1):
    return lambda history, i: side if i == at else None


FLAT = (100, 100, 100, 100)


def test_backtest_uses_stop_first_when_both_levels_hit():
    bars = frame([FLAT, (100, 103, 97, 100), FLAT])
    result = run_backtest(bars, once("long"), stop_distance=1, reward_risk=2)
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop"
    assert result.net_profit == pytest.approx(-1)


def test_empty_signal_returns_no_trades():
    result = run_backtest(frame([FLAT, FLAT]), lambda history, i: None, stop_distance=1)
    assert result.trades == ()
    assert result.net_profit == 0
    assert result.exposure_pct == 0


def test_signal_only_sees_past_bars():
    seen = []

    def signal(history, i):
        seen.append((len(history), i))
        return None

    run_backtest(frame([FLAT] * 5), signal, stop_distance=1)
    assert seen == [(1, 1), (2, 2), (3, 3)]


def test_target_hit_long_and_short():
    long_bars = frame([FLAT, (100, 100.5, 99.5, 100), (100, 102.5, 99.5, 102), FLAT])
    long = run_backtest(long_bars, once("long"), stop_distance=1, reward_risk=2)
    assert long.trades[0].exit_reason == "target"
    assert long.net_profit == pytest.approx(2)

    short_bars = frame([FLAT, (100, 100.5, 99.5, 100), (100, 100.5, 97.5, 98), FLAT])
    short = run_backtest(short_bars, once("short"), stop_distance=1, reward_risk=2)
    assert short.trades[0].exit_reason == "target"
    assert short.net_profit == pytest.approx(2)


def test_gap_through_stop_fills_at_worse_open():
    bars = frame([FLAT, (100, 100.5, 99.5, 100), (97, 97.5, 96.5, 97), FLAT])
    result = run_backtest(bars, once("long"), stop_distance=1, reward_risk=2)
    trade = result.trades[0]
    assert trade.exit_reason == "stop_gap"
    assert trade.exit == pytest.approx(97)
    assert result.net_profit == pytest.approx(-3)


def test_costs_are_charged_on_both_sides():
    bars = frame([FLAT, (100, 100.5, 99.9, 100), (100, 103, 99.9, 102), FLAT])
    result = run_backtest(bars, once("long"), stop_distance=1, reward_risk=2,
                          spread=0.2, slippage=0.05, commission_per_lot=7, volume=0.5,
                          price_unit_value=100)
    trade = result.trades[0]
    assert trade.entry == pytest.approx(100.15)
    # Target 102.15, exit pays half spread + slippage again: 102.00.
    assert trade.gross_pnl == pytest.approx(1.85 * 0.5 * 100)
    assert trade.costs == pytest.approx(3.5)
    assert trade.net_pnl == pytest.approx(92.5 - 3.5)


def test_time_exit_and_end_of_data():
    quiet = (100, 100.2, 99.8, 100.1)
    timed = run_backtest(frame([FLAT] + [quiet] * 6), once("long"), stop_distance=1,
                         max_holding_bars=2)
    assert timed.trades[0].exit_reason == "time_exit"
    assert timed.trades[0].bars_held == 2

    bars = frame([FLAT] + [quiet] * 3)
    open_end = run_backtest(bars, once("long"), stop_distance=1)
    assert open_end.trades[0].exit_reason == "end_of_data"
    assert open_end.trades[0].exit_time == bars.index[-1]


def test_one_position_at_a_time_and_metrics():
    loser = (100, 100.2, 98.5, 99)
    winner = (100, 102.5, 99.8, 102)
    bars = frame([FLAT, loser, loser, winner, FLAT])
    result = run_backtest(bars, lambda history, i: "long", stop_distance=1, reward_risk=2)
    assert [t.exit_reason for t in result.trades] == ["stop", "stop", "target"]
    assert result.worst_losing_streak == 2
    assert result.win_rate == pytest.approx(1 / 3)
    assert result.average_loss == pytest.approx(1)
    assert result.average_win == pytest.approx(2)
    assert result.profit_factor == pytest.approx(1)
    assert result.max_drawdown_pct == pytest.approx(2 / 10_000 * 100)
    assert result.exposure_pct == pytest.approx(60)


@pytest.mark.parametrize("kwargs", [
    {"stop_distance": 0}, {"stop_distance": 1, "spread": -0.1},
    {"stop_distance": 1, "volume": math.nan}, {"stop_distance": 1, "max_holding_bars": 0},
    {"stop_distance": 1, "price_unit_value": 0},
    {"stop_distance": 1, "max_holding_bars": math.nan},
])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        run_backtest(frame([FLAT, FLAT, FLAT]), once("long"), **kwargs)


def test_rejects_bad_bars():
    with pytest.raises(ValueError):
        run_backtest(frame([FLAT, (100, 99, 101, 100), FLAT]), once("long"), stop_distance=1)
    with pytest.raises(ValueError):
        run_backtest(frame([FLAT, (100, math.nan, 99, 100), FLAT]), once("long"),
                     stop_distance=1)
