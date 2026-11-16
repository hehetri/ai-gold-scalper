"""Dual-agent pre-trade review ("four-eyes" control).

Every proposed operation is tested by two independent, deterministic agents:

* ``RiskAnalystAgent``  - account gates, position sizing, projected loss, margin.
* ``ExecutionValidatorAgent`` - quote quality, price/volume normalisation, broker
  stop distances, closed-candle signal freshness and an independent loss
  recomputation cross-checked against the broker's own estimate.

A proposal is approved only when *both* agents approve. Any veto, missing
datum or internal error rejects it. These agents are plain Python rules, not
LLMs: an LLM never authorises a trade. This module never submits orders; an
approval is an input to a separately gated execution layer.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite
from typing import Literal, Protocol

from .mt5_market_data import SymbolSnapshot
from .risk import (
    RiskLimits,
    RiskRejected,
    RiskState,
    SizingSpec,
    calculate_position_size,
    is_multiple_of,
    risk_gate_violations,
)

logger = logging.getLogger(__name__)

Side = Literal["long", "short"]
Mode = Literal["backtest", "paper", "demo", "live"]
# Allow-lists: anything not named here gets the strictest treatment.
_APPROVABLE_MODES = ("backtest", "paper", "demo")
_OFFLINE_MODES = ("backtest", "paper")
_MAX_BROKER_LOSS_TOLERANCE = 0.10


def _needs_broker_data(mode: object) -> bool:
    return not (type(mode) is str and mode in _OFFLINE_MODES)


def _context_is_genuine(ctx: ReviewContext) -> bool:
    """Exact types only: duck-typed limits/state/symbol could bypass validation."""
    return (
        type(ctx.limits) is RiskLimits
        and type(ctx.state) is RiskState
        and type(ctx.symbol) is SymbolSnapshot
    )


def _distance(a: float, b: float) -> Decimal:
    """Exact decimal a - b, so on-the-limit prices do not fail on float noise."""
    return Decimal(str(a)) - Decimal(str(b))


@dataclass(frozen=True)
class TradeProposal:
    """A candidate operation produced by a strategy. It carries no authority."""

    symbol: str
    side: Side
    entry_price: float
    stop_price: float
    target_price: float
    volume: float
    signal_bar_close_time: datetime  # close time of the completed bar behind the signal
    created_at: datetime


@dataclass(frozen=True)
class ReviewContext:
    """Everything the agents may look at. All datetimes must be timezone-aware."""

    mode: Mode
    now: datetime
    symbol: SymbolSnapshot
    bid: float
    ask: float
    quote_time: datetime | None
    limits: RiskLimits
    state: RiskState
    signal_max_age_seconds: float
    allow_new_orders: bool = False
    cost_per_lot: float = 0.0
    # Positive cash loss from order_calc_profit, computed from the executable
    # quote (ask for a long, bid for a short) to the stop.
    broker_loss_estimate: float | None = None
    required_margin: float | None = None  # from order_calc_margin
    free_margin: float | None = None
    broker_loss_tolerance: float = 0.05


@dataclass(frozen=True)
class AgentVerdict:
    agent: str
    approved: bool
    reasons: tuple[str, ...]
    checks_run: tuple[str, ...]


@dataclass(frozen=True)
class ReviewDecision:
    approved: bool
    mode: Mode
    proposal: TradeProposal
    verdicts: tuple[AgentVerdict, ...]

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(f"{v.agent}: {r}" for v in self.verdicts for r in v.reasons)

    def to_record(self) -> dict[str, object]:
        """JSON-serialisable audit record."""
        proposal = asdict(self.proposal)
        for key in ("signal_bar_close_time", "created_at"):
            proposal[key] = str(proposal[key])
        return {
            "event": "trade_review",
            "approved": self.approved,
            "mode": self.mode,
            "proposal": proposal,
            "verdicts": [asdict(v) for v in self.verdicts],
        }


class ReviewAgent(Protocol):
    name: str

    def review(self, proposal: TradeProposal, ctx: ReviewContext) -> AgentVerdict: ...


class _Checklist:
    """Collects failures instead of stopping at the first one."""

    def __init__(self) -> None:
        self.reasons: list[str] = []
        self.checks: list[str] = []

    def require(self, check: str, ok: bool, reason: str) -> bool:
        if check not in self.checks:
            self.checks.append(check)
        if not ok:
            self.reasons.append(reason)
        return ok

    def verdict(self, agent: str) -> AgentVerdict:
        return AgentVerdict(agent, not self.reasons, tuple(self.reasons), tuple(self.checks))


def _finite(*values: object) -> bool:
    return all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in values
    )


def _aware(*values: datetime | None) -> bool:
    return all(isinstance(v, datetime) and v.tzinfo is not None for v in values)


class RiskAnalystAgent:
    """Agent 1: is this operation affordable for the account right now?"""

    name = "risk_analyst"

    def review(self, proposal: TradeProposal, ctx: ReviewContext) -> AgentVerdict:
        c = _Checklist()
        if not c.require("context_types", _context_is_genuine(ctx),
                         "Limits, state or symbol are not the validated types"):
            return c.verdict(self.name)
        limits, state = ctx.limits, ctx.state

        gate_reasons = risk_gate_violations(limits, state)
        c.checks.append("account_gates")
        c.reasons.extend(gate_reasons)

        prices_ok = c.require(
            "inputs_finite",
            _finite(proposal.entry_price, proposal.stop_price, proposal.target_price,
                    proposal.volume, ctx.cost_per_lot, ctx.bid, ctx.ask)
            and proposal.volume > 0
            and proposal.side in ("long", "short"),
            "Proposal prices/volume and quote must be finite, volume positive, side valid",
        )
        if not prices_ok or not _finite(state.current_equity) or state.current_equity <= 0:
            return c.verdict(self.name)

        risk_distance = abs(proposal.entry_price - proposal.stop_price)
        reward_distance = abs(proposal.target_price - proposal.entry_price)
        c.require(
            "reward_risk",
            risk_distance > 0 and reward_distance / risk_distance >= limits.min_reward_risk,
            f"Reward/risk is below the minimum {limits.min_reward_risk}",
        )

        # Risk is measured from the worse of the proposed entry and the price the
        # order can actually fill at now (ask for a long, bid for a short).
        fill_price = (
            max(proposal.entry_price, ctx.ask) if proposal.side == "long"
            else min(proposal.entry_price, ctx.bid)
        )
        try:
            sizing = calculate_position_size(SizingSpec(
                equity=state.current_equity,
                risk_fraction=limits.max_risk_per_trade_pct / 100,
                entry_price=fill_price,
                stop_price=proposal.stop_price,
                tick_size=ctx.symbol.trade_tick_size,
                tick_value=ctx.symbol.trade_tick_value,
                volume_min=ctx.symbol.volume_min,
                volume_max=ctx.symbol.volume_max,
                volume_step=ctx.symbol.volume_step,
                cost_per_lot=ctx.cost_per_lot,
            ))
        except RiskRejected as exc:
            c.require("position_sizing", False, f"Sizing rejected: {exc}")
            return c.verdict(self.name)

        c.require(
            "position_sizing",
            proposal.volume <= sizing.volume,
            f"Volume {proposal.volume} exceeds the risk-budget maximum {sizing.volume}",
        )
        loss_if_stopped = sizing.estimated_cash_risk / sizing.volume * proposal.volume
        broker = ctx.broker_loss_estimate
        if broker is not None:
            # Project with the worse of the local and broker figures.
            if c.require(
                "broker_loss",
                _finite(broker) and broker > 0,
                "Broker loss estimate is invalid",
            ):
                loss_if_stopped = max(
                    loss_if_stopped, broker + ctx.cost_per_lot * proposal.volume
                )
        equity_after = state.current_equity - loss_if_stopped
        if _finite(state.day_start_equity, state.peak_equity):
            c.require(
                "projected_daily_loss",
                equity_after >= state.day_start_equity * (1 - limits.max_daily_loss_pct / 100),
                "A stop-out would breach the daily loss limit",
            )
            c.require(
                "projected_drawdown",
                equity_after >= state.peak_equity * (1 - limits.max_total_drawdown_pct / 100),
                "A stop-out would breach the maximum drawdown limit",
            )

        required, free = ctx.required_margin, ctx.free_margin
        if _needs_broker_data(ctx.mode) or required is not None or free is not None:
            c.require(
                "margin",
                required is not None
                and free is not None
                and _finite(required, free)
                and 0 < required <= free * limits.max_margin_usage_pct / 100,
                "Margin data is missing/invalid or required margin exceeds the usage limit",
            )
        return c.verdict(self.name)


class ExecutionValidatorAgent:
    """Agent 2: is this operation well-formed and executable as specified?

    Deliberately does not reuse the sizing code used by the risk analyst, so a
    defect in one implementation is caught by the other.
    """

    name = "execution_validator"

    def review(self, proposal: TradeProposal, ctx: ReviewContext) -> AgentVerdict:
        c = _Checklist()
        if not c.require("context_types", _context_is_genuine(ctx),
                         "Limits, state or symbol are not the validated types"):
            return c.verdict(self.name)
        sym, limits = ctx.symbol, ctx.limits

        c.require(
            "mode",
            type(ctx.mode) is str and ctx.mode in _APPROVABLE_MODES,
            f"Mode {ctx.mode!r} is not approved (live trading is not approved in this system)",
        )
        if _needs_broker_data(ctx.mode):
            c.require("mode", ctx.allow_new_orders is True, "allow_new_orders is disabled")
        symbol_ok = c.require(
            "symbol_metadata",
            _finite(sym.point, sym.trade_tick_size, sym.trade_tick_value, sym.volume_min,
                    sym.volume_max, sym.volume_step, sym.trade_stops_level,
                    sym.trade_freeze_level)
            and min(sym.point, sym.trade_tick_size, sym.trade_tick_value, sym.volume_min,
                    sym.volume_step) > 0
            and sym.volume_max >= sym.volume_min
            and min(sym.trade_stops_level, sym.trade_freeze_level) >= 0,
            "Broker symbol metadata is missing or invalid",
        )
        c.require("symbol", proposal.symbol == sym.name, "Proposal symbol differs from snapshot")
        c.require("side", proposal.side in ("long", "short"), "Side must be 'long' or 'short'")

        numbers_ok = c.require(
            "inputs_finite",
            _finite(proposal.entry_price, proposal.stop_price, proposal.target_price,
                    proposal.volume, ctx.bid, ctx.ask, ctx.cost_per_lot,
                    ctx.signal_max_age_seconds, ctx.broker_loss_tolerance)
            and min(proposal.entry_price, proposal.stop_price, proposal.target_price,
                    proposal.volume) > 0
            and ctx.cost_per_lot >= 0
            and ctx.signal_max_age_seconds > 0
            and 0 <= ctx.broker_loss_tolerance <= _MAX_BROKER_LOSS_TOLERANCE,
            "Proposal, quote and tolerance numbers must be finite and within range",
        )
        times_ok = c.require(
            "timestamps",
            _aware(ctx.now, ctx.quote_time, proposal.signal_bar_close_time, proposal.created_at),
            "Timestamps are missing or not timezone-aware",
        )
        if (
            not numbers_ok or not times_ok or not symbol_ok
            or proposal.side not in ("long", "short")
        ):
            return c.verdict(self.name)
        assert ctx.quote_time is not None

        # Quote quality, recomputed from raw bid/ask rather than trusted from state.
        spread = ctx.ask - ctx.bid
        quote_ok = c.require(
            "quote", ctx.bid > 0 and spread >= 0, "Invalid bid/ask (non-positive or crossed)"
        )
        c.require("quote", spread <= limits.max_spread_price, "Spread exceeds the limit")
        quote_age = (ctx.now - ctx.quote_time).total_seconds()
        c.require(
            "quote",
            -1 <= quote_age <= limits.max_quote_age_seconds,
            f"Quote is stale or from the future (age {quote_age:.3f}s)",
        )
        c.require(
            "state_consistency",
            ctx.state.spread_price is not None
            and _finite(ctx.state.spread_price)
            and abs(ctx.state.spread_price - spread) <= sym.trade_tick_size,
            "Risk-state spread contradicts the quote",
        )

        # Signal must come from a completed bar and still be fresh.
        signal_age = (ctx.now - proposal.signal_bar_close_time).total_seconds()
        c.require(
            "signal_freshness",
            0 <= signal_age <= ctx.signal_max_age_seconds,
            f"Signal bar is unfinished or expired (age {signal_age:.1f}s)",
        )
        c.require(
            "signal_freshness",
            proposal.signal_bar_close_time <= proposal.created_at <= ctx.now,
            "Proposal timestamp is inconsistent with its signal bar",
        )

        # Geometry and broker normalisation.
        if proposal.side == "long":
            geometry = proposal.stop_price < proposal.entry_price < proposal.target_price
            reference = ctx.ask
        else:
            geometry = proposal.target_price < proposal.entry_price < proposal.stop_price
            reference = ctx.bid
        c.require("geometry", geometry, "Stop/entry/target are on the wrong sides")
        if quote_ok:
            c.require(
                "entry_vs_quote",
                abs(proposal.entry_price - reference) <= limits.max_spread_price,
                "Entry price is too far from the executable quote",
            )
        c.require(
            "price_normalisation",
            all(is_multiple_of(p, sym.trade_tick_size)
                for p in (proposal.entry_price, proposal.stop_price, proposal.target_price)),
            "Prices are not aligned to the broker tick size",
        )
        c.require(
            "volume_normalisation",
            sym.volume_min <= proposal.volume <= sym.volume_max
            and is_multiple_of(proposal.volume, sym.volume_step),
            "Volume violates broker min/max/step",
        )
        # Brokers measure stops/freeze levels from the price the position would
        # close at (bid for a long, ask for a short). Require the distance from
        # both that quote and the entry, in exact decimal arithmetic.
        min_distance = (
            Decimal(max(sym.trade_stops_level, sym.trade_freeze_level))
            * Decimal(str(sym.point))
        )
        closing_quote = ctx.bid if proposal.side == "long" else ctx.ask
        sign = 1 if proposal.side == "long" else -1
        c.require(
            "stop_distance",
            all(
                sign * _distance(anchor, proposal.stop_price) >= min_distance
                and sign * _distance(proposal.target_price, anchor) >= min_distance
                for anchor in (proposal.entry_price, closing_quote)
            ),
            "Stop or target is inside the broker stops/freeze level",
        )

        # Independent loss recomputation and broker cross-check.
        equity = ctx.state.current_equity
        metadata_ok = c.require(
            "independent_loss",
            _finite(equity, sym.trade_tick_size, sym.trade_tick_value)
            and min(equity, sym.trade_tick_size, sym.trade_tick_value) > 0,
            "Equity or tick metadata is missing/invalid",
        )
        if metadata_ok:
            # Worst executable fill, not the (possibly optimistic) proposed entry.
            worst_fill = (
                max(proposal.entry_price, reference) if proposal.side == "long"
                else min(proposal.entry_price, reference)
            )
            ticks = abs(worst_fill - proposal.stop_price) / sym.trade_tick_size
            local_loss = (ticks * sym.trade_tick_value + ctx.cost_per_lot) * proposal.volume
            worst_loss = local_loss
            broker = ctx.broker_loss_estimate
            if _needs_broker_data(ctx.mode) or broker is not None:
                broker_ok = c.require(
                    "broker_loss_cross_check",
                    broker is not None and _finite(broker) and broker > 0,
                    "Broker loss estimate (order_calc_profit) is missing or invalid",
                )
                if broker_ok:
                    assert broker is not None
                    broker_total = broker + ctx.cost_per_lot * proposal.volume
                    c.require(
                        "broker_loss_cross_check",
                        abs(broker_total - local_loss)
                        <= ctx.broker_loss_tolerance * max(broker_total, local_loss),
                        "Local loss estimate disagrees with the broker estimate",
                    )
                    worst_loss = max(local_loss, broker_total)
            budget = equity * limits.max_risk_per_trade_pct / 100
            c.require(
                "independent_loss",
                worst_loss <= budget * (1 + 1e-9),
                f"Stop-out loss {worst_loss:.2f} exceeds the per-trade budget {budget:.2f}",
            )
        return c.verdict(self.name)


class DualAgentReview:
    """Runs both core agents and requires unanimous approval.

    The risk analyst and the execution validator are always instantiated here
    and cannot be replaced or removed. ``extra_agents`` can only add vetoes.
    """

    def __init__(self, extra_agents: Sequence[ReviewAgent] = ()) -> None:
        self._agents: tuple[ReviewAgent, ...] = (
            RiskAnalystAgent(), ExecutionValidatorAgent(), *extra_agents,
        )
        names = [agent.name for agent in self._agents]
        if len(set(names)) != len(names):
            raise ValueError("Extra agents must have names distinct from the core agents")

    def review(self, proposal: TradeProposal, ctx: ReviewContext) -> ReviewDecision:
        verdicts: list[AgentVerdict] = []
        for agent in self._agents:
            try:
                verdict = agent.review(proposal, ctx)
                if type(verdict) is not AgentVerdict:
                    raise TypeError("agent did not return an AgentVerdict")
            except Exception as exc:  # noqa: BLE001 - any agent failure is a veto
                verdict = AgentVerdict(
                    agent.name, False, (f"Agent error: {type(exc).__name__}: {exc}",), ()
                )
            verdicts.append(verdict)
        decision = ReviewDecision(
            approved=len(verdicts) >= 2 and all(
                v.approved is True and not v.reasons for v in verdicts
            ),
            mode=ctx.mode,
            proposal=proposal,
            verdicts=tuple(verdicts),
        )
        logger.info(json.dumps(decision.to_record(), sort_keys=True, default=str))
        return decision
