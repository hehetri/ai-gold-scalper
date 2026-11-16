# Claude Code repository rules

This project builds an XAUUSD scalping research/automation system for MetaTrader 5. Invoke `/ai-gold-scalper` for trading-system tasks.

## Safety
- Research/backtest by default; live trading disabled.
- Never enable live orders or remove/increase risk limits without explicit owner approval.
- Deterministic risk code has final veto authority. An LLM never directly authorizes or submits trades.
- Never hard-code broker credentials, account identifiers, tick values, contract sizes or Gold pip assumptions.
- No martingale, loss-recovery sizing or unbounded grids.
- Missing/stale account, symbol, quote or risk data means no trade.
- Every operation passes `review.DualAgentReview` (two deterministic agents, unanimous). Never reduce it to one agent or bypass it.

## Engineering
Inspect before editing. Keep data, strategy, risk, execution, backtesting and monitoring separate. Use typed modular Python, explicit config, structured logs and tests. Never claim tests passed unless run. Preserve user changes. Do not commit secrets. Closed-candle signals cannot use unfinished bars.

## Workflow
Changes to strategy, risk, review, execution, backtest, MT5 or config code must be verified by both project subagents, `gold-risk-auditor` and `gold-operation-tester`, run in parallel and independently; both must return APPROVE. Run `python -m pytest`, `python -m ruff check .` and `python -m mypy` first.

Read relevant docs, state assumptions, plan, implement, test, review safety, and report changed files/results/limitations. Respond in Brazilian Portuguese when the owner writes in Portuguese; keep code identifiers in English.
