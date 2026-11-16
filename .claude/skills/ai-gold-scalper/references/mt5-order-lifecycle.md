# MT5 order lifecycle

Validate terminal, account permissions, symbol, session, quote freshness, filling mode, margin and broker constraints before sending an order. Read digits, point, tick size/value, contract size, volume min/max/step, stops level and freeze level at runtime.

Use explicit states: CREATED, VALIDATED, SUBMITTED, ACCEPTED, PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED, UNKNOWN. Persist intent and broker IDs. For UNKNOWN after timeout/disconnect, reconnect and reconcile orders/deals/positions before retrying. Never blindly resubmit. Log result codes without secrets.
