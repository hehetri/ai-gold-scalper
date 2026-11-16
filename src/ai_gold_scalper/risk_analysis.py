"""Statistical risk analysis of a sequence of closed-trade results.

Deterministic for a given seed. The Monte Carlo step resamples trades as if
they were independent, which understates loss clustering; treat its output as
an optimistic bound, not a forecast. Nothing here predicts future performance.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RiskReport:
    trade_count: int
    win_rate: float
    average_win: float
    average_loss: float  # positive number
    payoff_ratio: float
    expectancy: float
    profit_factor: float
    net_profit: float
    max_drawdown_pct: float
    max_drawdown_duration_trades: int
    worst_losing_streak: int
    var_95: float  # per-trade loss not exceeded in 95% of trades (positive = loss)
    cvar_95: float  # mean loss of the worst 5% of trades
    mc_median_drawdown_pct: float
    mc_p95_drawdown_pct: float
    mc_prob_drawdown_breach: float
    mc_prob_net_loss: float
    drawdown_limit_pct: float
    sample_is_sufficient: bool
    warnings: tuple[str, ...]


def _max_drawdown_pct(equity_paths: np.ndarray, starting_equity: float) -> np.ndarray:
    """Max peak-to-trough drawdown (%) for each row of cumulative equity."""
    start = np.full((equity_paths.shape[0], 1), starting_equity)
    curve = np.concatenate([start, equity_paths], axis=1)
    peaks = np.maximum.accumulate(curve, axis=1)
    # A path at or below zero equity is a total loss.
    drawdown = np.where(curve <= 0, 100.0, (peaks - curve) / peaks * 100)
    return np.asarray(drawdown.max(axis=1))


def analyze_trades(
    net_pnls: Sequence[float],
    starting_equity: float,
    *,
    drawdown_limit_pct: float,
    simulations: int = 2000,
    seed: int = 7,
    min_trades: int = 100,
) -> RiskReport:
    """Summarise realised trade P/L (account currency, net of all costs)."""
    pnl = np.asarray(list(net_pnls), dtype=float)
    if pnl.size == 0:
        raise ValueError("At least one trade is required")
    if not np.isfinite(pnl).all():
        raise ValueError("Trade results must be finite numbers")
    if starting_equity <= 0 or not 0 < drawdown_limit_pct < 100:
        raise ValueError("starting_equity must be positive and 0 < drawdown_limit_pct < 100")
    if simulations < 1 or min_trades < 1:
        raise ValueError("simulations and min_trades must be at least 1")

    wins, losses = pnl[pnl > 0], -pnl[pnl < 0]
    average_win = float(wins.mean()) if wins.size else 0.0
    average_loss = float(losses.mean()) if losses.size else 0.0
    gross_loss = float(losses.sum())
    if gross_loss:
        profit_factor = float(wins.sum()) / gross_loss
    else:
        profit_factor = float("inf") if wins.size else 0.0

    equity = starting_equity + np.cumsum(pnl)
    curve = np.concatenate([[starting_equity], equity])
    peaks = np.maximum.accumulate(curve)
    underwater = curve < peaks
    duration = longest = 0
    for flag in underwater:
        duration = duration + 1 if flag else 0
        longest = max(longest, duration)
    streak = worst_streak = 0
    for value in pnl:
        streak = streak + 1 if value < 0 else 0
        worst_streak = max(worst_streak, streak)

    loss_distribution = -pnl
    var_95 = float(np.quantile(loss_distribution, 0.95))
    tail = loss_distribution[loss_distribution >= var_95]
    cvar_95 = float(tail.mean())

    rng = np.random.default_rng(seed)
    samples = rng.choice(pnl, size=(simulations, pnl.size), replace=True)
    paths = starting_equity + np.cumsum(samples, axis=1)
    mc_drawdowns = _max_drawdown_pct(paths, starting_equity)

    warnings: list[str] = []
    sufficient = pnl.size >= min_trades
    if not sufficient:
        warnings.append(
            f"Only {pnl.size} trades (< {min_trades}): statistics are not reliable evidence"
        )
    if float(pnl.mean()) <= 0:
        warnings.append("Expectancy is not positive after costs")
    if wins.size and float(wins.max()) > 0.5 * float(wins.sum()) and wins.size > 1:
        warnings.append("More than half of gross profit comes from a single trade")

    return RiskReport(
        trade_count=int(pnl.size),
        win_rate=float(wins.size / pnl.size),
        average_win=average_win,
        average_loss=average_loss,
        payoff_ratio=average_win / average_loss if average_loss else float("inf"),
        expectancy=float(pnl.mean()),
        profit_factor=profit_factor,
        net_profit=float(pnl.sum()),
        max_drawdown_pct=float(_max_drawdown_pct(equity[None, :], starting_equity)[0]),
        max_drawdown_duration_trades=longest,
        worst_losing_streak=worst_streak,
        var_95=var_95,
        cvar_95=cvar_95,
        mc_median_drawdown_pct=float(np.median(mc_drawdowns)),
        mc_p95_drawdown_pct=float(np.quantile(mc_drawdowns, 0.95)),
        mc_prob_drawdown_breach=float((mc_drawdowns >= drawdown_limit_pct).mean()),
        mc_prob_net_loss=float((paths[:, -1] < starting_equity).mean()),
        drawdown_limit_pct=drawdown_limit_pct,
        sample_is_sufficient=sufficient,
        warnings=tuple(warnings),
    )
