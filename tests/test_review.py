import json
import logging
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai_gold_scalper.mt5_market_data import SymbolSnapshot
from ai_gold_scalper.review import (
    AgentVerdict,
    DualAgentReview,
    ExecutionValidatorAgent,
    ReviewContext,
    RiskAnalystAgent,
    TradeProposal,
)
from ai_gold_scalper.risk import RiskLimits, RiskState

NOW = datetime(2026, 3, 2, 14, 30, 5, tzinfo=UTC)
SYMBOL = SymbolSnapshot(
    name="XAUUSD.a", digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0,
    contract_size=100.0, volume_min=0.01, volume_max=100.0, volume_step=0.01,
    trade_stops_level=20, trade_freeze_level=0,
    currency_base="XAU", currency_profit="USD", currency_margin="USD",
)
STATE = RiskState(
    day_start_equity=10_000, peak_equity=10_000, current_equity=10_000,
    spread_price=0.2, quote_age_seconds=0.5,
)
# Long 0.10 lots, 2.00 stop -> 200 ticks * 1.0 * 0.10 = 20 cash = 0.20% of equity.
PROPOSAL = TradeProposal(
    symbol="XAUUSD.a", side="long", entry_price=2300.20, stop_price=2298.20,
    target_price=2303.20, volume=0.10,
    signal_bar_close_time=NOW - timedelta(seconds=5), created_at=NOW - timedelta(seconds=4),
)
CTX = ReviewContext(
    mode="paper", now=NOW, symbol=SYMBOL, bid=2300.00, ask=2300.20,
    quote_time=NOW - timedelta(milliseconds=500),
    limits=RiskLimits(max_spread_price=0.5), state=STATE, signal_max_age_seconds=20,
)


def review(proposal=PROPOSAL, ctx=CTX):
    return DualAgentReview().review(proposal, ctx)


def vetoing(decision):
    return {v.agent for v in decision.verdicts if not v.approved}


def test_valid_proposal_is_approved_by_both_agents():
    decision = review()
    assert decision.approved
    assert [v.agent for v in decision.verdicts] == ["risk_analyst", "execution_validator"]
    assert all(v.checks_run for v in decision.verdicts)
    assert decision.reasons == ()


def test_valid_short_is_approved():
    short = replace(PROPOSAL, side="short", entry_price=2300.00, stop_price=2302.00,
                    target_price=2297.00)
    assert review(short).approved


def test_oversized_volume_is_vetoed_by_both_agents_independently():
    decision = review(replace(PROPOSAL, volume=0.20))  # 40 cash > 25 budget
    assert not decision.approved
    assert vetoing(decision) == {"risk_analyst", "execution_validator"}


def test_one_veto_is_enough():
    # Mis-aligned stop price: only the execution validator objects.
    decision = review(replace(PROPOSAL, stop_price=2298.205))
    assert not decision.approved
    assert vetoing(decision) == {"execution_validator"}


@pytest.mark.parametrize(("proposal_changes", "ctx_changes", "agent", "fragment"), [
    ({}, {"state": replace(STATE, paused=True)}, "risk_analyst", "paused"),
    ({}, {"state": replace(STATE, trades_today=3)}, "risk_analyst", "trades per day"),
    ({"target_price": 2301.20}, {}, "risk_analyst", "Reward/risk"),
    # Equity already near the daily floor (9900): a 20 stop-out would breach it.
    ({}, {"state": replace(STATE, current_equity=9_910)}, "risk_analyst", "daily loss"),
    ({}, {"required_margin": 6_000.0, "free_margin": 10_000.0}, "risk_analyst", "Margin"),
    ({}, {"required_margin": 100.0}, "risk_analyst", "Margin"),
    ({}, {"mode": "live", "allow_new_orders": True}, "execution_validator",
     "live trading is not approved"),
    ({}, {"mode": "demo"}, "execution_validator", "allow_new_orders"),
    ({"symbol": "XAUUSD"}, {}, "execution_validator", "symbol"),
    ({}, {"quote_time": None}, "execution_validator", "Timestamps"),
    ({}, {"quote_time": NOW - timedelta(seconds=10)}, "execution_validator", "stale"),
    ({}, {"bid": 2300.30}, "execution_validator", "crossed"),
    ({}, {"bid": 2299.00}, "execution_validator", "Spread exceeds"),
    ({}, {"state": replace(STATE, spread_price=0.05)}, "execution_validator", "contradicts"),
    ({"signal_bar_close_time": NOW + timedelta(seconds=30)}, {}, "execution_validator",
     "unfinished or expired"),
    ({"signal_bar_close_time": NOW - timedelta(seconds=90)}, {}, "execution_validator",
     "unfinished or expired"),
    ({"stop_price": 2302.20}, {}, "execution_validator", "wrong sides"),
    ({"entry_price": 2305.20, "stop_price": 2303.20, "target_price": 2308.20}, {},
     "execution_validator", "too far from the executable quote"),
    ({"volume": 0.105}, {}, "execution_validator", "min/max/step"),
    ({"stop_price": 2300.10, "target_price": 2300.40}, {}, "execution_validator",
     "stops/freeze level"),
    ({}, {"broker_loss_estimate": 30.0}, "execution_validator", "disagrees with the broker"),
    ({"entry_price": math.nan}, {}, "execution_validator", "finite"),
    ({"created_at": NOW.replace(tzinfo=None)}, {}, "execution_validator", "Timestamps"),
])
def test_rejections(proposal_changes, ctx_changes, agent, fragment):
    decision = review(replace(PROPOSAL, **proposal_changes), replace(CTX, **ctx_changes))
    assert not decision.approved
    reasons = [r for v in decision.verdicts if v.agent == agent for r in v.reasons]
    assert any(fragment in r for r in reasons), decision.reasons


def test_demo_requires_broker_loss_and_margin():
    demo = replace(CTX, mode="demo", allow_new_orders=True)
    rejected = review(ctx=demo)
    assert vetoing(rejected) == {"risk_analyst", "execution_validator"}

    approved = review(ctx=replace(demo, broker_loss_estimate=20.0, required_margin=230.0,
                                  free_margin=10_000.0))
    assert approved.approved


def test_broker_estimate_is_used_when_worse_than_local():
    # Broker 25.9 vs local 20.0 differ by more than the 5% tolerance -> veto.
    assert not review(ctx=replace(CTX, broker_loss_estimate=25.9)).approved
    # Within tolerance but pushes a borderline trade over budget.
    borderline = replace(PROPOSAL, volume=0.12)  # local loss 24.0, budget 25.0
    assert review(borderline).approved
    over = review(borderline, replace(CTX, broker_loss_estimate=25.2))
    assert vetoing(over) == {"execution_validator"}


def test_agent_exception_is_a_veto():
    class Broken:
        name = "broken"

        def review(self, proposal, ctx):
            raise RuntimeError("boom")

    decision = DualAgentReview([Broken()]).review(PROPOSAL, CTX)
    assert not decision.approved
    assert "Agent error" in decision.verdicts[2].reasons[0]


def test_inconsistent_verdict_cannot_approve():
    class Sloppy:
        name = "sloppy"

        def review(self, proposal, ctx):
            return AgentVerdict(self.name, True, ("but something is wrong",), ())

    assert not DualAgentReview([Sloppy()]).review(PROPOSAL, CTX).approved


def test_core_agents_cannot_be_replaced_or_duplicated():
    class YesMan:
        name = "yes_man"

        def review(self, proposal, ctx):
            return AgentVerdict(self.name, True, (), ("nothing",))

    oversized = replace(PROPOSAL, volume=0.20)
    decision = DualAgentReview([YesMan()]).review(oversized, CTX)
    assert not decision.approved
    assert [v.agent for v in decision.verdicts][:2] == ["risk_analyst", "execution_validator"]

    renamed = RiskAnalystAgent()
    renamed.name = "x"
    misaligned = replace(PROPOSAL, stop_price=2298.205)
    assert not DualAgentReview([renamed]).review(misaligned, CTX).approved

    for duplicate in (RiskAnalystAgent(), ExecutionValidatorAgent()):
        with pytest.raises(ValueError):
            DualAgentReview([duplicate])
    with pytest.raises(ValueError):
        DualAgentReview([YesMan(), YesMan()])


@pytest.mark.parametrize("mode", ["LIVE", "Live", "real", "demo ", "Demo", "", None, 1])
def test_unknown_modes_fail_closed(mode):
    full = replace(CTX, mode=mode, allow_new_orders=True, broker_loss_estimate=20.0,
                   required_margin=230.0, free_margin=10_000.0)
    decision = review(ctx=full)
    assert not decision.approved
    assert any("not approved" in r for r in decision.reasons)
    # Without broker data an unknown mode is also treated as broker-connected.
    assert vetoing(review(ctx=replace(CTX, mode=mode))) == {
        "risk_analyst", "execution_validator"
    }


@pytest.mark.parametrize("value", [None, math.nan, 1, "yes"])
def test_non_boolean_flags_fail_closed(value):
    assert not review(ctx=replace(CTX, state=replace(STATE, paused=value))).approved
    demo = replace(CTX, mode="demo", allow_new_orders=value, broker_loss_estimate=20.0,
                   required_margin=230.0, free_margin=10_000.0)
    assert not review(ctx=demo).approved


def test_projected_floors_use_the_worse_broker_estimate():
    # Local loss 20.0 keeps equity at 9900.5 (floor 9900); broker 20.9 does not.
    near_floor = replace(CTX, state=replace(STATE, current_equity=9_920.5))
    assert review(ctx=near_floor).approved
    decision = review(ctx=replace(near_floor, broker_loss_estimate=20.9))
    assert "risk_analyst" in vetoing(decision)
    assert any("daily loss" in r for r in decision.reasons)


@pytest.mark.parametrize("tolerance", [0.11, 0.5, 1e9, -0.01, math.nan])
def test_broker_tolerance_is_capped(tolerance):
    ctx = replace(CTX, broker_loss_estimate=20.0, broker_loss_tolerance=tolerance)
    assert vetoing(review(ctx=ctx)) == {"execution_validator"}


def test_stops_level_is_measured_from_the_closing_quote():
    # Stops level 0.20. Long stop 0.30 under entry (ask) but only 0.10 under bid.
    long = replace(PROPOSAL, stop_price=2299.90, target_price=2300.60, volume=0.01)
    assert vetoing(review(long)) == {"execution_validator"}
    short = replace(PROPOSAL, side="short", entry_price=2300.00, stop_price=2300.30,
                    target_price=2299.60, volume=0.01)
    assert vetoing(review(short)) == {"execution_validator"}


def test_stop_exactly_on_stops_level_is_accepted():
    # Zero spread so entry and closing quote coincide; 0.20 == 20 points exactly.
    ctx = replace(CTX, bid=2300.20, state=replace(STATE, spread_price=0.0))
    exact = replace(PROPOSAL, stop_price=2300.00, target_price=2300.40, volume=0.01)
    assert review(exact, ctx).approved
    inside = replace(PROPOSAL, stop_price=2300.01, target_price=2300.40, volume=0.01)
    assert not review(inside, ctx).approved


def test_loss_is_measured_from_the_executable_quote_not_an_optimistic_entry():
    # Budget 25. Entry 0.50 inside the quote makes the paper loss 25.00, but a
    # long fills at the ask (2300.20) and a short at the bid (2300.00): 37.50.
    demo = replace(CTX, mode="demo", allow_new_orders=True, required_margin=230.0,
                   free_margin=9_500.0)
    long = replace(PROPOSAL, entry_price=2299.70, stop_price=2298.70, target_price=2301.20,
                   volume=0.25)
    short = replace(PROPOSAL, side="short", entry_price=2300.50, stop_price=2301.50,
                    target_price=2299.00, volume=0.25)
    for proposal in (long, short):
        assert vetoing(review(proposal)) == {"risk_analyst", "execution_validator"}
        for broker in (25.0, 37.5):
            decision = review(proposal, replace(demo, broker_loss_estimate=broker))
            assert vetoing(decision) == {"risk_analyst", "execution_validator"}
        # The same geometry is fine once volume fits the real 1.50 distance.
        assert review(replace(proposal, volume=0.16)).approved


def test_duck_typed_limits_and_malformed_verdicts_are_vetoed():
    class FakeLimits:
        def __getattr__(self, name):
            return 99.0

    decision = review(ctx=replace(CTX, limits=FakeLimits()))
    assert vetoing(decision) == {"risk_analyst", "execution_validator"}

    class ReturnsNone:
        name = "returns_none"

        def review(self, proposal, ctx):
            return None

    decision = DualAgentReview([ReturnsNone()]).review(PROPOSAL, CTX)
    assert not decision.approved
    assert "Agent error" in decision.verdicts[2].reasons[0]

    class Evil(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            return True

    assert not review(ctx=replace(CTX, mode=Evil("live"))).approved


@pytest.mark.parametrize("changes", [
    {"point": 0.0}, {"point": -0.01}, {"point": math.inf},
    {"trade_freeze_level": math.nan}, {"trade_stops_level": -5},
    {"trade_tick_value": math.nan}, {"volume_step": 0.0},
])
def test_invalid_symbol_metadata_is_vetoed(changes):
    decision = review(ctx=replace(CTX, symbol=replace(SYMBOL, **changes)))
    assert "execution_validator" in vetoing(decision)


def test_decision_is_logged_as_json_audit_record(caplog):
    with caplog.at_level(logging.INFO, logger="ai_gold_scalper.review"):
        decision = review(replace(PROPOSAL, volume=0.20))
    record = json.loads(caplog.records[-1].getMessage())
    assert record["event"] == "trade_review"
    assert record["approved"] is False
    assert record == json.loads(json.dumps(decision.to_record(), default=str))
