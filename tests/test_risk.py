import math

import pytest

from ai_gold_scalper.risk import (
    RiskLimits,
    RiskRejected,
    RiskState,
    SizingSpec,
    calculate_position_size,
    is_multiple_of,
    risk_gate_violations,
    round_volume_down,
    validate_trade_allowed,
)

LIMITS = RiskLimits(max_spread_price=0.5)


def spec(**overrides):
    base = dict(
        equity=10_000, risk_fraction=0.01, entry_price=2000, stop_price=1999,
        tick_size=0.01, tick_value=1, volume_min=0.01, volume_max=100, volume_step=0.01,
    )
    return SizingSpec(**{**base, **overrides})


def state(**overrides):
    base = dict(
        day_start_equity=10_000, peak_equity=10_000, current_equity=10_000,
        spread_price=0.2, quote_age_seconds=0.5,
    )
    return RiskState(**{**base, **overrides})


def test_position_size_rounds_down_to_broker_step():
    result = calculate_position_size(spec())
    assert result.volume == 1.0
    assert result.estimated_cash_risk <= result.risk_budget


def test_position_size_never_rounds_up():
    # budget 100 / loss-per-lot 300 = 0.333... -> 0.33, not 0.34
    result = calculate_position_size(spec(stop_price=1997))
    assert result.volume == 0.33
    assert result.estimated_cash_risk == pytest.approx(99.0)


def test_costs_reduce_volume():
    without = calculate_position_size(spec())
    with_costs = calculate_position_size(spec(cost_per_lot=25))
    assert with_costs.volume == 0.8
    assert with_costs.volume < without.volume
    assert with_costs.estimated_cash_risk <= with_costs.risk_budget


def test_volume_capped_at_broker_maximum():
    assert calculate_position_size(spec(volume_max=0.5)).volume == 0.5


def test_rejects_when_minimum_lot_exceeds_budget():
    with pytest.raises(RiskRejected, match="below broker minimum"):
        calculate_position_size(spec(equity=100, risk_fraction=0.001,
                                     volume_min=0.1, volume_step=0.1))


@pytest.mark.parametrize("overrides", [
    {"equity": math.nan}, {"equity": 0}, {"risk_fraction": 0}, {"risk_fraction": 1},
    {"stop_price": 2000}, {"stop_price": -1}, {"tick_size": 0}, {"tick_value": math.inf},
    {"volume_step": 0}, {"volume_max": 0.001}, {"cost_per_lot": -1}, {"tick_value": None},
])
def test_sizing_fails_closed_on_invalid_inputs(overrides):
    with pytest.raises(RiskRejected):
        calculate_position_size(spec(**overrides))


def test_round_volume_down_handles_tiny_and_scientific_steps():
    assert round_volume_down(0.30000000000000004, 0.1) == 0.3
    assert round_volume_down(0.123456789, 1e-05) == 0.12345
    assert round_volume_down(0.999, 1) == 0.0


def test_is_multiple_of():
    assert is_multiple_of(2300.10, 0.01)
    assert not is_multiple_of(2300.105, 0.01)
    assert not is_multiple_of(math.nan, 0.01)


def test_healthy_state_is_allowed():
    assert risk_gate_violations(LIMITS, state()) == ()
    validate_trade_allowed(LIMITS, state())


@pytest.mark.parametrize(("overrides", "message"), [
    ({"paused": True}, "paused"),
    ({"current_equity": 9_899}, "Daily loss"),
    ({"day_start_equity": 9_700, "current_equity": 9_690}, "drawdown"),
    ({"consecutive_losses": 3}, "consecutive losses"),
    ({"trades_today": 3}, "trades per day"),
    ({"open_positions": 1}, "open positions"),
    ({"spread_price": 0.51}, "Spread"),
    ({"spread_price": None}, "Spread is missing"),
    ({"spread_price": math.nan}, "Spread is missing"),
    ({"quote_age_seconds": None}, "Quote age is missing"),
    ({"quote_age_seconds": 3.1}, "stale"),
    ({"quote_age_seconds": -5}, "stale"),
    ({"current_equity": math.nan}, "Equity state"),
    ({"peak_equity": math.inf}, "Equity state"),
    ({"current_equity": 10_500}, "Contradictory"),
    ({"day_start_equity": 10_050}, "Contradictory"),
    ({"paused": None}, "pause state is unknown"),
    ({"trades_today": -1}, "counters"),
])
def test_each_gate_rejects(overrides, message):
    with pytest.raises(RiskRejected, match=message):
        validate_trade_allowed(LIMITS, state(**overrides))


def test_all_violations_are_reported_together():
    reasons = risk_gate_violations(LIMITS, state(paused=True, trades_today=9, spread_price=None))
    assert len(reasons) == 3


@pytest.mark.parametrize("kwargs", [
    {"max_spread_price": 0}, {"max_spread_price": math.nan},
    {"max_spread_price": 0.5, "max_risk_per_trade_pct": 2.0},  # above daily limit
    {"max_spread_price": 0.5, "max_daily_loss_pct": 5.0},  # above total drawdown
    {"max_spread_price": 0.5, "max_open_positions": 0},
    {"max_spread_price": 0.5, "max_open_positions": 1.5},
    {"max_spread_price": 0.5, "max_margin_usage_pct": 101},
])
def test_incoherent_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        RiskLimits(**kwargs)
