"""Deterministic risk controls. This module never submits orders."""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite


class RiskRejected(ValueError):
    """A proposed trade violates configured risk constraints."""


@dataclass(frozen=True)
class SizingSpec:
    equity: float
    risk_fraction: float
    entry_price: float
    stop_price: float
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float


@dataclass(frozen=True)
class SizingResult:
    volume: float
    estimated_cash_risk: float
    risk_budget: float


def calculate_position_size(spec: SizingSpec) -> SizingResult:
    """Size down to broker volume step using tick value in account currency.

    Assumes tick_value is the cash P/L for one lot per one tick, as reported
    by the broker. For instruments with asymmetric profit/loss tick values or
    currency conversion complexities, validate with MT5 order_calc_profit
    before allowing an order.
    """
    values = (
        spec.equity, spec.risk_fraction, spec.entry_price, spec.stop_price,
        spec.tick_size, spec.tick_value, spec.volume_min, spec.volume_max,
        spec.volume_step,
    )
    if not all(isfinite(float(v)) for v in values):
        raise RiskRejected("All sizing inputs must be finite numbers")
    if spec.equity <= 0 or not 0 < spec.risk_fraction < 1:
        raise RiskRejected("Equity must be positive and risk_fraction between 0 and 1")
    if spec.entry_price <= 0 or spec.stop_price <= 0 or spec.entry_price == spec.stop_price:
        raise RiskRejected("Entry and stop must be positive and different")
    if spec.tick_size <= 0 or spec.tick_value <= 0:
        raise RiskRejected("Broker tick size and tick value must be positive")
    if spec.volume_min <= 0 or spec.volume_step <= 0 or spec.volume_max < spec.volume_min:
        raise RiskRejected("Invalid broker volume constraints")

    ticks_to_stop = abs(spec.entry_price - spec.stop_price) / spec.tick_size
    loss_per_lot = ticks_to_stop * spec.tick_value
    budget = spec.equity * spec.risk_fraction
    raw_volume = budget / loss_per_lot
    capped = min(raw_volume, spec.volume_max)
    steps = floor((capped + 1e-12) / spec.volume_step)
    volume = steps * spec.volume_step
    # Decimal rounding avoids values such as 0.30000000000000004.
    decimals = max(0, len(str(spec.volume_step).split(".")[-1].rstrip("0")))
    volume = round(volume, decimals)
    if volume < spec.volume_min:
        raise RiskRejected(
            f"Risk budget supports {volume} lots, below broker minimum {spec.volume_min}"
        )
    estimated = loss_per_lot * volume
    if estimated > budget + max(1e-8, budget * 1e-9):
        raise RiskRejected("Rounded volume exceeds the configured risk budget")
    return SizingResult(volume, estimated, budget)


@dataclass(frozen=True)
class RiskLimits:
    max_daily_loss_pct: float = 1.0
    max_total_drawdown_pct: float = 3.0
    max_consecutive_losses: int = 3
    max_trades_per_day: int = 3
    max_open_positions: int = 1
    max_spread_price: float = 0.50


@dataclass(frozen=True)
class RiskState:
    day_start_equity: float
    peak_equity: float
    current_equity: float
    consecutive_losses: int = 0
    trades_today: int = 0
    open_positions: int = 0
    spread_price: float = 0.0
    paused: bool = False


def validate_trade_allowed(limits: RiskLimits, state: RiskState) -> None:
    """Raise RiskRejected when any deterministic account-level gate fails."""
    if state.paused:
        raise RiskRejected("Trading is paused (kill switch)")
    if min(state.day_start_equity, state.peak_equity, state.current_equity) <= 0:
        raise RiskRejected("Equity state must be positive")
    if state.day_start_equity and (
        state.current_equity <= state.day_start_equity * (1 - limits.max_daily_loss_pct / 100)
    ):
        raise RiskRejected("Daily loss limit reached")
    if state.current_equity <= state.peak_equity * (1 - limits.max_total_drawdown_pct / 100):
        raise RiskRejected("Maximum drawdown limit reached")
    if state.consecutive_losses >= limits.max_consecutive_losses:
        raise RiskRejected("Maximum consecutive losses reached")
    if state.trades_today >= limits.max_trades_per_day:
        raise RiskRejected("Maximum trades per day reached")
    if state.open_positions >= limits.max_open_positions:
        raise RiskRejected("Maximum open positions reached")
    if state.spread_price < 0 or state.spread_price > limits.max_spread_price:
        raise RiskRejected("Spread is outside the permitted range")
