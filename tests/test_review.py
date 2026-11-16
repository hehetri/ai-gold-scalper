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
    ({}, {"mode": "live", "allow_new_orders": True}, "execution_validator", "Live trading"),
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

    decision = DualAgentReview([RiskAnalystAgent(), Broken()]).review(PROPOSAL, CTX)
    assert not decision.approved
    assert "Agent error" in decision.verdicts[1].reasons[0]


def test_inconsistent_verdict_cannot_approve():
    class Sloppy:
        name = "sloppy"

        def review(self, proposal, ctx):
            return AgentVerdict(self.name, True, ("but something is wrong",), ())

    assert not DualAgentReview([RiskAnalystAgent(), Sloppy()]).review(PROPOSAL, CTX).approved


def test_requires_two_distinct_agents():
    with pytest.raises(ValueError):
        DualAgentReview([RiskAnalystAgent()])
    with pytest.raises(ValueError):
        DualAgentReview([RiskAnalystAgent(), RiskAnalystAgent()])
    DualAgentReview([RiskAnalystAgent(), ExecutionValidatorAgent()])


def test_decision_is_logged_as_json_audit_record(caplog):
    with caplog.at_level(logging.INFO, logger="ai_gold_scalper.review"):
        decision = review(replace(PROPOSAL, volume=0.20))
    record = json.loads(caplog.records[-1].getMessage())
    assert record["event"] == "trade_review"
    assert record["approved"] is False
    assert record == json.loads(json.dumps(decision.to_record(), default=str))
