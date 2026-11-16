"""Small deterministic OHLC backtester for research, not a broker simulator."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from typing import Literal

import pandas as pd

from .indicators import validate_ohlc

Side = Literal["long", "short"]
SignalFn = Callable[[pd.DataFrame, int], Side | None]


@dataclass(frozen=True)
class Trade:
    side: Side
    entry_time: object
    exit_time: object
    entry: float
    exit: float
    stop: float
    target: float
    gross_pnl: float  # after spread/slippage, before commission
    costs: float  # commission
    net_pnl: float
    exit_reason: str
    bars_held: int


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[Trade, ...]
    starting_equity: float
    ending_equity: float
    net_profit: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    expectancy: float
    average_win: float
    average_loss: float
    worst_losing_streak: int
    exposure_pct: float


def run_backtest(
    bars: pd.DataFrame,
    signal: SignalFn,
    *,
    stop_distance: float,
    reward_risk: float = 1.5,
    spread: float = 0.0,
    slippage: float = 0.0,
    commission_per_lot: float = 0.0,
    volume: float = 1.0,
    starting_equity: float = 10_000.0,
    price_unit_value: float = 1.0,
    max_holding_bars: int | None = None,
) -> BacktestResult:
    """Replay one position at a time; the signal sees only bars before index i.

    * Entry at the open of bar i with adverse half-spread plus slippage.
    * Stop and target are checked from the entry bar onwards. If both are
      touched in one candle the stop wins (conservative).
    * A bar that opens beyond the stop fills at that worse open (gap), never at
      the stop price. Targets never receive price improvement.
    * ``max_holding_bars`` closes at that bar's close; otherwise positions
      still open at the end close on the last bar.
    * ``price_unit_value`` is the account-currency value of a 1.0 price move
      for one lot (tick_value / tick_size from the broker). The default of 1.0
      reports P/L in price units times volume.

    Bars are treated as mid prices with a constant spread. This is a research
    harness; use tick data for execution-quality validation.
    """
    validate_ohlc(bars)
    numbers = (stop_distance, reward_risk, spread, slippage, commission_per_lot, volume,
               starting_equity, price_unit_value)
    if not all(isfinite(v) for v in numbers):
        raise ValueError("backtest parameters must be finite")
    if min(stop_distance, reward_risk, volume, starting_equity, price_unit_value) <= 0:
        raise ValueError(
            "stop_distance, reward_risk, volume, starting_equity and price_unit_value "
            "must be positive"
        )
    if min(spread, slippage, commission_per_lot) < 0:
        raise ValueError("execution costs cannot be negative")
    if max_holding_bars is not None and (
        type(max_holding_bars) is not int or max_holding_bars < 1
    ):
        raise ValueError("max_holding_bars must be an integer of at least 1")

    half_cost = spread / 2 + slippage
    last = len(bars) - 1
    trades: list[Trade] = []
    bars_in_market = 0
    i = 1
    while i < last:
        side = signal(bars.iloc[:i].copy(), i)
        if side not in ("long", "short"):
            i += 1
            continue
        direction = 1.0 if side == "long" else -1.0
        entry = float(bars.iloc[i].open) + direction * half_cost
        stop = entry - direction * stop_distance
        target = entry + direction * stop_distance * reward_risk

        j = i
        while True:
            candle = bars.iloc[j]
            opened, high, low = float(candle.open), float(candle.high), float(candle.low)
            adverse, favourable = (low, high) if side == "long" else (high, low)
            if (adverse - stop) * direction <= 0:
                gapped = j > i and (opened - stop) * direction < 0
                raw_exit, reason = (opened, "stop_gap") if gapped else (stop, "stop")
                break
            if (favourable - target) * direction >= 0:
                raw_exit, reason = target, "target"
                break
            if max_holding_bars is not None and j - i + 1 >= max_holding_bars:
                raw_exit, reason = float(candle.close), "time_exit"
                break
            if j == last:
                raw_exit, reason = float(candle.close), "end_of_data"
                break
            j += 1

        exit_price = raw_exit - direction * half_cost
        gross = (exit_price - entry) * direction * volume * price_unit_value
        costs = commission_per_lot * volume
        held = j - i + 1
        bars_in_market += held
        trades.append(Trade(side, bars.index[i], bars.index[j], entry, exit_price, stop,
                            target, gross, costs, gross - costs, reason, held))
        i = j + 1

    equity = peak = starting_equity
    max_dd = 0.0
    streak = worst_streak = 0
    for trade in trades:
        equity += trade.net_pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, 100.0 if equity <= 0 else (peak - equity) / peak * 100)
        streak = streak + 1 if trade.net_pnl < 0 else 0
        worst_streak = max(worst_streak, streak)
    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [-t.net_pnl for t in trades if t.net_pnl < 0]
    gross_loss = sum(losses)
    net = sum(t.net_pnl for t in trades)
    return BacktestResult(
        trades=tuple(trades),
        starting_equity=starting_equity,
        ending_equity=starting_equity + net,
        net_profit=net,
        win_rate=len(wins) / len(trades) if trades else 0.0,
        profit_factor=sum(wins) / gross_loss if gross_loss else (float("inf") if wins else 0.0),
        max_drawdown_pct=max_dd,
        expectancy=net / len(trades) if trades else 0.0,
        average_win=sum(wins) / len(wins) if wins else 0.0,
        average_loss=gross_loss / len(losses) if losses else 0.0,
        worst_losing_streak=worst_streak,
        exposure_pct=bars_in_market / len(bars) * 100,
    )
