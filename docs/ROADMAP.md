# Roadmap

## Foundation — implemented
- [x] Architecture, safety rules, Claude Code skill and reference docs.
- [x] Python package, example configuration and repository instructions.
- [x] CI workflow for unit tests, Ruff and strict mypy.
- [x] Typed configuration loader that rejects live mode.
- [x] Reviewer subagents `gold-risk-auditor` and `gold-operation-tester`.

## Research and market data — baseline implemented
- [x] Pure EMA/RSI indicators and OHLC validation.
- [x] M5 directional context and M1 closed-candle pullback trigger.
- [x] Optional read-only MT5 adapter for symbol discovery, metadata, quotes and completed bars.
- [ ] Historical data storage, gap detection and data-quality reports.
- [ ] Tick-level data ingestion and replay.

## Risk — baseline implemented
- [x] Deterministic volume sizing using broker tick metadata and volume constraints.
- [x] Daily loss, total drawdown, consecutive-loss, trade-count, open-position and spread vetoes.
- [x] Fail-closed gates for missing, non-finite and contradictory state; costs included in sizing.
- [x] Dual-agent pre-trade review with projected-loss, margin and broker loss cross-checks.
- [x] Trade risk analysis: VaR/CVaR, drawdown duration, losing streaks, Monte Carlo drawdown.
- [x] Read-only MT5 loss and margin estimates (order_calc_profit / order_calc_margin).
- [ ] Verify those estimates against a real broker terminal (not possible in CI).
- [ ] Persistent risk state and restart-safe kill switch.
- [ ] Slippage and aggregate exposure limits.

## Backtesting — baseline implemented
- [x] Deterministic OHLC replay with spread, slippage and commission inputs.
- [x] Conservative stop-first handling when both stop and target are touched in one candle.
- [x] Gap-through-stop fills, time exits, account-currency conversion input.
- [ ] Tick-accurate execution model, swaps, latency and partial fills.
- [ ] Chronological out-of-sample, walk-forward and parameter-stability reports.

## Execution and demo
- [ ] MT5 order state machine and persistent order intents.
- [ ] Duplicate-order prevention and restart reconciliation.
- [ ] Demo-only execution adapter, monitoring, alerts and forward testing.

## Live readiness
Live is not an automatic milestone. Require explicit owner approval and documented evidence for every live-trading gate in `.claude/skills/ai-gold-scalper/SKILL.md`. Until then, keep order submission disabled.
