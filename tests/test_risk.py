import pytest

from ai_gold_scalper.risk import (
    RiskLimits, RiskRejected, RiskState, SizingSpec,
    calculate_position_size, validate_trade_allowed,
)


def test_position_size_rounds_down_to_broker_step():
    result = calculate_position_size(SizingSpec(
        equity=10_000, risk_fraction=0.01, entry_price=2000, stop_price=1999,
        tick_size=0.01, tick_value=1, volume_min=0.01, volume_max=100, volume_step=0.01,
    ))
    assert result.volume == 1.0
    assert result.estimated_cash_risk <= result.risk_budget


def test_rejects_when_minimum_lot_exceeds_budget():
    with pytest.raises(RiskRejected):
        calculate_position_size(SizingSpec(
            equity=100, risk_fraction=0.001, entry_price=2000, stop_price=1999,
            tick_size=0.01, tick_value=1, volume_min=0.1, volume_max=100, volume_step=0.1,
        ))


def test_daily_loss_gate():
    with pytest.raises(RiskRejected, match="Daily loss"):
        validate_trade_allowed(RiskLimits(), RiskState(
            day_start_equity=10_000, peak_equity=10_000, current_equity=9_899,
        ))


def test_kill_switch_gate():
    with pytest.raises(RiskRejected, match="paused"):
        validate_trade_allowed(RiskLimits(), RiskState(
            day_start_equity=10_000, peak_equity=10_000, current_equity=10_000, paused=True,
        ))
