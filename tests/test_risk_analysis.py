import math

import pytest

from ai_gold_scalper.risk_analysis import analyze_trades


def test_basic_statistics():
    report = analyze_trades([100, -50, -50, 200, -100], 10_000, drawdown_limit_pct=3)
    assert report.trade_count == 5
    assert report.win_rate == pytest.approx(0.4)
    assert report.average_win == pytest.approx(150)
    assert report.average_loss == pytest.approx(200 / 3)
    assert report.payoff_ratio == pytest.approx(2.25)
    assert report.expectancy == pytest.approx(20)
    assert report.profit_factor == pytest.approx(1.5)
    assert report.net_profit == pytest.approx(100)
    assert report.worst_losing_streak == 2
    # Peak 10100 -> 10000 after two losses.
    assert report.max_drawdown_pct == pytest.approx(100 / 10_100 * 100)
    assert report.max_drawdown_duration_trades == 2
    assert report.var_95 == pytest.approx(90)
    assert report.cvar_95 == pytest.approx(100)


def test_small_sample_and_negative_expectancy_are_flagged():
    report = analyze_trades([-10, 5, -10], 1_000, drawdown_limit_pct=3)
    assert not report.sample_is_sufficient
    assert any("not reliable" in w for w in report.warnings)
    assert any("Expectancy" in w for w in report.warnings)


def test_monte_carlo_is_deterministic_and_bounded():
    pnls = [30, -20, 45, -20, -20, 60, -20, 30] * 20
    first = analyze_trades(pnls, 10_000, drawdown_limit_pct=3, seed=11)
    second = analyze_trades(pnls, 10_000, drawdown_limit_pct=3, seed=11)
    assert first == second
    assert first.sample_is_sufficient
    assert 0 <= first.mc_median_drawdown_pct <= first.mc_p95_drawdown_pct <= 100
    assert 0 <= first.mc_prob_drawdown_breach <= 1
    assert 0 <= first.mc_prob_net_loss <= 1


def test_only_losses_always_breach_and_ruin_is_capped():
    report = analyze_trades([-100] * 20, 1_000, drawdown_limit_pct=3, simulations=50)
    assert report.profit_factor == 0
    assert report.max_drawdown_pct == 100
    assert report.mc_prob_drawdown_breach == 1
    assert report.mc_prob_net_loss == 1


def test_only_wins():
    report = analyze_trades([10, 20], 1_000, drawdown_limit_pct=3, simulations=10)
    assert math.isinf(report.profit_factor)
    assert report.max_drawdown_pct == 0
    assert report.worst_losing_streak == 0


@pytest.mark.parametrize(("pnls", "kwargs"), [
    ([], {}), ([1.0, math.nan], {}), ([1.0], {"starting_equity": 0}),
    ([1.0], {"drawdown_limit_pct": 0}), ([1.0], {"simulations": 0}),
    ([1.0], {"starting_equity": math.nan}), ([1.0], {"starting_equity": math.inf}),
    ([1.0], {"drawdown_limit_pct": math.nan}),
])
def test_invalid_inputs(pnls, kwargs):
    params = {"starting_equity": 1_000, "drawdown_limit_pct": 3, **kwargs}
    with pytest.raises(ValueError):
        analyze_trades(pnls, params.pop("starting_equity"), **params)
