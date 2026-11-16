# MetaTrader 5 integration

Confirm current vendor docs, broker and terminal environment before implementation. The official Python package normally targets a compatible local Windows MT5 terminal; do not assume Linux/macOS compatibility.

At startup validate terminal connection, account permissions, symbol visibility/name/trade mode, session, fresh bid/ask, tick size/value, digits, point, contract size, volume min/max/step, stops/freeze levels, filling mode and margin.

Model order states: CREATED, VALIDATED, SUBMITTED, ACCEPTED, PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED, UNKNOWN. Persist intents and broker IDs. On timeout/disconnect, reconcile orders/deals/positions before retry; never blindly resubmit. Normalize price/volume from broker metadata. Never commit credentials, account IDs or secrets; use local environment variables.
