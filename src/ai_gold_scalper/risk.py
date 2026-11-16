"""Deterministic risk controls with final veto authority.

This module never submits orders and never consults an LLM. Every function
fails closed: missing, non-finite or contradictory inputs reject the trade.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import ROUND_DOWN, Decimal
from math import isfinite


class RiskRejected(ValueError):
    """A proposed trade violates configured risk constraints."""


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return isfinite(value)


def round_volume_down(volume: float, step: float) -> float:
    """Round ``volume`` down to a multiple of the broker ``step`` (never up)."""
    if not _is_finite_number(volume) or not _is_finite_number(step) or step <= 0 or volume < 0:
        raise RiskRejected("Volume and volume step must be finite and step positive")
    step_dec = Decimal(str(step))
    steps = (Decimal(str(volume)) / step_dec).to_integral_value(rounding=ROUND_DOWN)
    return float(steps * step_dec)


def is_multiple_of(value: float, step: float) -> bool:
    """True when ``value`` is an exact multiple of ``step`` in decimal arithmetic."""
    if not _is_finite_number(value) or not _is_finite_number(step) or step <= 0:
        return False
    return Decimal(str(value)) % Decimal(str(step)) == 0


def stop_loss_per_lot(
    entry_price: float, stop_price: float, tick_size: float, tick_value: float
) -> float:
    """Cash loss for one lot if the stop is hit, from broker tick metadata."""
    values = (entry_price, stop_price, tick_size, tick_value)
    if not all(_is_finite_number(v) for v in values):
        raise RiskRejected("Entry, stop and tick metadata must be finite numbers")
    if entry_price <= 0 or stop_price <= 0 or entry_price == stop_price:
        raise RiskRejected("Entry and stop must be positive and different")
    if tick_size <= 0 or tick_value <= 0:
        raise RiskRejected("Broker tick size and tick value must be positive")
    return abs(entry_price - stop_price) / tick_size * tick_value


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
    # Expected round-turn cash cost per lot (commission plus any spread/slippage
    # not already inside the entry/stop prices). Counted against the budget.
    cost_per_lot: float = 0.0


@dataclass(frozen=True)
class SizingResult:
    volume: float
    estimated_cash_risk: float
    risk_budget: float


def calculate_position_size(spec: SizingSpec) -> SizingResult:
    """Largest broker-valid volume whose stop loss plus costs fits the budget.

    Assumes ``tick_value`` is the account-currency P/L of one lot per tick as
    reported by the broker. Cross-check the result against MT5
    ``order_calc_profit`` before any order: tick values can be asymmetric and
    depend on currency conversion.
    """
    if not all(_is_finite_number(getattr(spec, f.name)) for f in fields(spec)):
        raise RiskRejected("All sizing inputs must be finite numbers")
    if spec.equity <= 0 or not 0 < spec.risk_fraction < 1:
        raise RiskRejected("Equity must be positive and risk_fraction between 0 and 1")
    if spec.volume_min <= 0 or spec.volume_step <= 0 or spec.volume_max < spec.volume_min:
        raise RiskRejected("Invalid broker volume constraints")
    if spec.cost_per_lot < 0:
        raise RiskRejected("cost_per_lot cannot be negative")

    loss_per_lot = (
        stop_loss_per_lot(spec.entry_price, spec.stop_price, spec.tick_size, spec.tick_value)
        + spec.cost_per_lot
    )
    budget = spec.equity * spec.risk_fraction
    volume = round_volume_down(min(budget / loss_per_lot, spec.volume_max), spec.volume_step)
    if volume < spec.volume_min:
        raise RiskRejected(
            f"Risk budget supports {volume} lots, below broker minimum {spec.volume_min}"
        )
    estimated = loss_per_lot * volume
    if estimated > budget * (1 + 1e-9):
        raise RiskRejected("Rounded volume exceeds the configured risk budget")
    return SizingResult(volume, estimated, budget)


@dataclass(frozen=True)
class RiskLimits:
    """Account-level limits. ``max_spread_price`` is broker specific: no default."""

    max_spread_price: float
    max_risk_per_trade_pct: float = 0.25
    max_daily_loss_pct: float = 1.0
    max_total_drawdown_pct: float = 3.0
    max_consecutive_losses: int = 3
    max_trades_per_day: int = 3
    max_open_positions: int = 1
    max_quote_age_seconds: float = 3.0
    min_reward_risk: float = 1.0
    max_margin_usage_pct: float = 50.0

    def __post_init__(self) -> None:
        if not all(_is_finite_number(getattr(self, f.name)) for f in fields(self)):
            raise ValueError("All risk limits must be finite numbers")
        if not 0 < self.max_risk_per_trade_pct <= self.max_daily_loss_pct:
            raise ValueError("Require 0 < max_risk_per_trade_pct <= max_daily_loss_pct")
        if not self.max_daily_loss_pct <= self.max_total_drawdown_pct < 100:
            raise ValueError("Require max_daily_loss_pct <= max_total_drawdown_pct < 100")
        if min(self.max_consecutive_losses, self.max_trades_per_day, self.max_open_positions) < 1:
            raise ValueError("Count limits must be at least 1")
        if self.max_spread_price <= 0 or self.max_quote_age_seconds <= 0:
            raise ValueError("Spread and quote-age limits must be positive")
        if self.min_reward_risk <= 0 or not 0 < self.max_margin_usage_pct <= 100:
            raise ValueError("Invalid reward/risk or margin-usage limit")


@dataclass(frozen=True)
class RiskState:
    """Snapshot of account/market state. ``None`` means unknown and blocks trading."""

    day_start_equity: float
    peak_equity: float
    current_equity: float  # includes floating P/L
    spread_price: float | None = None
    quote_age_seconds: float | None = None
    consecutive_losses: int = 0
    trades_today: int = 0
    open_positions: int = 0
    paused: bool = False


def risk_gate_violations(limits: RiskLimits, state: RiskState) -> tuple[str, ...]:
    """Return every violated account-level gate; an empty tuple means allowed."""
    reasons: list[str] = []
    if state.paused:
        reasons.append("Trading is paused (kill switch)")

    equities = (state.day_start_equity, state.peak_equity, state.current_equity)
    if not all(_is_finite_number(v) and v > 0 for v in equities):
        reasons.append("Equity state must be finite and positive")
    else:
        if state.current_equity > state.peak_equity:
            reasons.append("Contradictory equity state: current equity above recorded peak")
        if state.current_equity <= state.day_start_equity * (1 - limits.max_daily_loss_pct / 100):
            reasons.append("Daily loss limit reached")
        if state.current_equity <= state.peak_equity * (1 - limits.max_total_drawdown_pct / 100):
            reasons.append("Maximum drawdown limit reached")

    counters = (state.consecutive_losses, state.trades_today, state.open_positions)
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in counters):
        reasons.append("Trade counters must be non-negative integers")
    else:
        if state.consecutive_losses >= limits.max_consecutive_losses:
            reasons.append("Maximum consecutive losses reached")
        if state.trades_today >= limits.max_trades_per_day:
            reasons.append("Maximum trades per day reached")
        if state.open_positions >= limits.max_open_positions:
            reasons.append("Maximum open positions reached")

    if state.spread_price is None or not _is_finite_number(state.spread_price):
        reasons.append("Spread is missing or invalid")
    elif not 0 <= state.spread_price <= limits.max_spread_price:
        reasons.append("Spread is outside the permitted range")

    if state.quote_age_seconds is None or not _is_finite_number(state.quote_age_seconds):
        reasons.append("Quote age is missing or invalid")
    elif not -1 <= state.quote_age_seconds <= limits.max_quote_age_seconds:
        reasons.append("Quote is stale or from the future")
    return tuple(reasons)


def validate_trade_allowed(limits: RiskLimits, state: RiskState) -> None:
    """Raise RiskRejected when any deterministic account-level gate fails."""
    reasons = risk_gate_violations(limits, state)
    if reasons:
        raise RiskRejected("; ".join(reasons))
