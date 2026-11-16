# Architecture

## Components
1. Market data: historical bars/live ticks, timestamp and freshness validation.
2. Features: indicators computed only from available past/current data.
3. Strategy: structured candidate signal, rationale, invalidation and expiry.
4. Risk manager: broker-aware sizing and final veto.
5. Execution: MT5 order submission only in explicitly enabled mode.
6. State/reconciliation: persistent intents and MT5 reconciliation after restart.
7. Backtester: chronological replay with costs and deterministic fill assumptions.
8. Monitoring: health checks, structured logs, alerts, kill switch and audit trail.

## Flow
```text
MT5/history -> validation -> M5 context + M1 trigger -> candidate
                                                   -> deterministic risk gate
                                                   -> execution adapter (OFF by default)
                                                   -> MT5 + reconciliation + journal
```

Research/backtesting must run without an MT5 terminal. Keep MT5 integration optional behind interfaces. Use explicit modes: backtest, paper, demo, live; default is backtest. Live mode requires separate approval and startup checks.
