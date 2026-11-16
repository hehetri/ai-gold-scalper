# Risk management

Risk is deterministic, independently tested and has final veto authority.

Calculate cash loss at the proposed stop from actual broker metadata/MT5 calculation facilities; never assume a universal XAUUSD pip value. Include account-currency conversion where required. Round volume DOWN to broker step. If below minimum, reject rather than round up.

Required configurable limits: risk per trade, daily realized plus floating loss, total drawdown, consecutive losses, trades/day, open positions/exposure, spread, slippage, free margin and quote age.

Provide persistent pause/kill switch and document whether existing positions remain open or are liquidated; do not silently choose. Fail closed if account, quote, symbol, stop, margin or risk data is missing/stale/invalid. No martingale, doubling, loss-recovery sizing or unbounded grid.

## Implemented

- `risk.py`: cost-inclusive sizing, decimal round-down, coherent limits, gates that reject `None`/`NaN`/contradictory state.
- `review.py`: dual-agent review; projected stop-out loss checked against daily and drawdown floors; margin usage; broker loss cross-check.
- `risk_analysis.py`: expectancy, payoff, profit factor, drawdown and duration, losing streak, VaR/CVaR 95%, seeded Monte Carlo drawdown (independent-trade bootstrap, an optimistic bound).
- `config.py`: caps on limits; `risk.enabled` cannot be false; `max_spread_price` has no default.

Not implemented: persistent kill switch, restart reconciliation, aggregate exposure and slippage limits.
