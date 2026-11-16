"""Small deterministic OHLC backtester for research, not a broker simulator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Literal

import pandas as pd

Side = Literal["long", "short"]


@dataclass(frozen=True)
class Trade:
    side: Side
    entry_time: object
    exit_time: object
    entry: float
    exit: float
    stop: float
    target: float
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: str


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


def run_backtest(
    bars: pd.DataFrame,
    signal: Callable[[pd.DataFrame, int], Side | None],
    *,
    stop_distance: float,
    reward_risk: float = 1.5,
    spread: float = 0.0,
    slippage: float = 0.0,
    commission_per_lot: float = 0.0,
    volume: float = 1.0,
    starting_equity: float = 10_000.0,
) -> BacktestResult:
    """Replay one position at a time; signals use bars up to index i-1.

    Entry is at the next bar open with adverse half-spread/slippage. Stops and
    targets are checked on subsequent bars. If both are touched in one OHLC
    candle, stop wins (conservative). Costs are price-unit spread/slippage
    multiplied by volume plus round-turn commission. This is a simplified
    research harness; use tick data for final execution-quality validation.
    """
    required = {"open", "high", "low", "close"}
    if not required.issubset(bars.columns) or bars.empty:
        raise ValueError(f"bars must be non-empty and contain {sorted(required)}")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("bars index must be chronological and unique")
    if stop_distance <= 0 or reward_risk <= 0 or volume <= 0 or starting_equity <= 0:
        raise ValueError("stop_distance, reward_risk, volume and starting_equity must be positive")
    if min(spread, slippage, commission_per_lot) < 0:
        raise ValueError("execution costs cannot be negative")

    trades: list[Trade] = []
    i = 1
    while i < len(bars) - 1:
        side = signal(bars.iloc[:i].copy(), i)
        if side not in ("long", "short"):
            i += 1
            continue
        row = bars.iloc[i]
        half_cost = spread / 2 + slippage
        entry = float(row.open) + half_cost if side == "long" else float(row.open) - half_cost
        stop = entry - stop_distance if side == "long" else entry + stop_distance
        target_distance = stop_distance * reward_risk
        target = entry + target_distance if side == "long" else entry - target_distance
        exit_price = float(bars.iloc[-1].close)
        exit_time = bars.index[-1]
        reason = "end_of_data"
        j = i
        while j < len(bars):
            candle = bars.iloc[j]
            if side == "long":
                stop_hit = float(candle.low) <= stop
                target_hit = float(candle.high) >= target
            else:
                stop_hit = float(candle.high) >= stop
                target_hit = float(candle.low) <= target
            if stop_hit:
                exit_price, exit_time, reason = stop, bars.index[j], "stop"
                break
            if target_hit:
                exit_price, exit_time, reason = target, bars.index[j], "target"
                break
            j += 1
        exit_price = exit_price - half_cost if side == "long" else exit_price + half_cost
        gross = (exit_price - entry) * volume if side == "long" else (entry - exit_price) * volume
        costs = commission_per_lot * volume
        trades.append(Trade(side, bars.index[i], exit_time, entry, exit_price, stop, target,
                            gross, costs, gross - costs, reason))
        i = max(i + 1, j + 1)

    equity = starting_equity
    peak = equity
    max_dd = 0.0
    for trade in trades:
        equity += trade.net_pnl
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100)
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
    )
