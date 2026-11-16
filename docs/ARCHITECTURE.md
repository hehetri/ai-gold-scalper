# Architecture

## Components
1. Market data: historical bars/live ticks, timestamp and freshness validation.
2. Features: indicators computed only from available past/current data.
3. Strategy: structured candidate signal, rationale, invalidation and expiry.
4. Risk manager: broker-aware sizing and final veto.
   Dual-agent review (`review.py`): a risk analyst and an execution validator test every candidate independently; both must approve.
5. Execution: MT5 order submission only in explicitly enabled mode.
6. State/reconciliation: persistent intents and MT5 reconciliation after restart.
7. Backtester: chronological replay with costs and deterministic fill assumptions.
8. Monitoring: health checks, structured logs, alerts, kill switch and audit trail.

## Flow
```text
MT5/history -> validation -> M5 context + M1 trigger -> candidate
                                                   -> dual-agent review
                                                      (risk analyst + execution validator, unanimous)
                                                   -> execution adapter (OFF by default)
                                                   -> MT5 + reconciliation + journal
```

Research/backtesting must run without an MT5 terminal. Keep MT5 integration optional behind interfaces. Use explicit modes: backtest, paper, demo, live; default is backtest. Live mode requires separate approval and startup checks.

## Dual control

No single component can approve an operation. At runtime `DualAgentReview` needs two distinct deterministic agents to agree, and an agent error counts as a veto. In development, code changes on the trading path need `APPROVE` from both Claude Code subagents (`gold-risk-auditor`, `gold-operation-tester`). Neither layer involves an LLM in a real-time trading decision.
