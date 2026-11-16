# Risk controls

Risk is deterministic, tested independently and has final veto authority.

## Sizing (`risk.calculate_position_size`)

- Loss per lot = price distance to stop / broker tick size x broker tick value,
  plus expected round-turn cost per lot. All from runtime broker metadata.
- Volume is rounded **down** to the broker step with decimal arithmetic. Below
  the broker minimum the trade is rejected; it is never rounded up.
- Cross-check with `MT5MarketData.estimate_stop_loss` (`order_calc_profit`).
  Tick values can be asymmetric and depend on account-currency conversion; use
  the worse of the two figures.

## Account gates (`risk.risk_gate_violations`)

Kill switch, daily loss, total drawdown, consecutive losses, trades per day,
open positions, spread, quote age. Unknown (`None`) or non-finite values
reject. Equity above the recorded peak is treated as contradictory state.

Limits must stay coherent: per-trade <= daily <= total drawdown. The config
loader also caps them and refuses `risk.enabled: false`. `max_spread_price` has
no default; it must be set from the broker's observed spread.

## Writing a gate

`NaN` compares false with everything, so `if value > limit: reject` lets `NaN`
through. Validate finiteness first, then compare. Every new gate needs tests for
`None`, `NaN`, `inf`, zero, negative, exactly-on-limit and just-over-limit.

## Risk analysis (`risk_analysis.analyze_trades`)

Input: net trade P/L in account currency. Output: win rate, payoff, expectancy,
profit factor, max drawdown and duration, worst losing streak, VaR/CVaR 95%,
and a seeded bootstrap of drawdown (median, 95th percentile, probability of
breaching the drawdown limit, probability of a net loss).

The bootstrap treats trades as independent, so it understates loss clustering:
read it as an optimistic bound. Below the minimum sample the report is flagged
as not reliable evidence.

## Still to build

Persistent pause/kill-switch state, restart reconciliation, aggregate exposure
and slippage limits. Until they exist, demo execution is not ready.

## Never

Martingale, doubling, loss-recovery or streak-based size increases, averaging
down, unbounded grids, hard-coded pip or tick values, an LLM in the approval
path.
