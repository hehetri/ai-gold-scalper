# Risk controls reference

Risk is deterministic and has final veto authority. Compute stop-loss cash risk using actual broker tick size/value, contract size, account currency and MT5 calculation APIs. Never hard-code a universal Gold pip value.

Round volume down to broker step. If below minimum, reject. Validate max volume, stops/freeze levels, margin, spread, slippage, quote age and aggregate exposure. Enforce per-trade, daily, overall drawdown, consecutive-loss and trade-count limits. Persist kill switch and pause state. Reconcile on restart. Fail closed on stale/invalid state. Never use martingale or loss-recovery sizing.
