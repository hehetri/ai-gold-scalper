# Roadmap

## Foundation
- [x] Architecture, safety rules, Claude Code skill and reference docs.
- [ ] Confirm broker, exact symbol, account currency and MT5 environment.

## Data/research
- [ ] Historical/live data adapter and timestamp validation.
- [ ] Normalized M1/M5 storage, feature calculations and signal audit.

## Backtest
- [ ] Event-driven simulator with spread/commission/slippage.
- [ ] Chronological splits, walk-forward, metrics and stress tests.
- [ ] Review for look-ahead bias and overfitting.

## Risk
- [ ] Broker-aware position sizing and daily/drawdown lockouts.
- [ ] Persistent kill switch, reconciliation and edge-case tests.

## Demo
- [ ] MT5 demo adapter, order state machine, monitoring and forward test.

## Live readiness
Live is not an automatic milestone. Require explicit owner approval and documented evidence for every live-trading gate in the skill.
