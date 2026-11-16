# Roadmap

## Foundation — implemented
- [x] Architecture, safety rules, Claude Code skill and reference docs.
- [x] Python package, example configuration and repository instructions.
- [x] CI workflow for unit tests.

## Research and market data — baseline implemented
- [x] Pure EMA/RSI indicators and OHLC validation.
- [x] M5 directional context and M1 closed-candle pullback trigger.
- [x] Optional read-only MT5 adapter for symbol discovery, metadata, quotes and completed bars.
- [ ] Historical data storage, gap detection and data-quality reports.
- [ ] Tick-level data ingestion and replay.

## Risk — baseline implemented
- [x] Deterministic volume sizing using broker tick metadata and volume constraints.
- [x] Daily loss, total drawdown, consecutive-loss, trade-count, open-position and spread vetoes.
- [ ] Broker-specific loss verification using MT5 order_calc_profit and account-currency conversion.
- [ ] Persistent risk state and restart-safe kill switch.
- [ ] Margin, slippage and exposure checks integrated with account state.

## Backtesting — baseline implemented
- [x] Deterministic OHLC replay with spread, slippage and commission inputs.
- [x] Conservative stop-first handling when both stop and target are touched in one candle.
- [ ] Tick-accurate execution model, swaps, latency and partial fills.
- [ ] Chronological out-of-sample, walk-forward and parameter-stability reports.

## Execution and demo
- [ ] MT5 order state machine and persistent order intents.
- [ ] Duplicate-order prevention and restart reconciliation.
- [ ] Demo-only execution adapter, monitoring, alerts and forward testing.

## Live readiness
Live is not an automatic milestone. Require explicit owner approval and documented evidence for every live-trading gate in `.claude/skills/ai-gold-scalper/SKILL.md`. Until then, keep order submission disabled.
