# MetaTrader 5 integration

Confirm current vendor docs, broker and terminal environment before implementation. The official Python package normally targets a compatible local Windows MT5 terminal; do not assume Linux/macOS compatibility.

At startup validate terminal connection, account permissions, symbol visibility/name/trade mode, session, fresh bid/ask, tick size/value, digits, point, contract size, volume min/max/step, stops/freeze levels, filling mode and margin.

Model order states: CREATED, VALIDATED, SUBMITTED, ACCEPTED, PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED, UNKNOWN. Persist intents and broker IDs. On timeout/disconnect, reconcile orders/deals/positions before retry; never blindly resubmit. Normalize price/volume from broker metadata. Never commit credentials, account IDs or secrets; use local environment variables.

## Read-only adapter

`MT5MarketData` offers symbol resolution, symbol snapshot, quote, completed bars, `account_snapshot` (no login or server), `estimate_stop_loss` (`order_calc_profit`) and `estimate_margin` (`order_calc_margin`). The two estimates are calculations; nothing is sent. MT5 timestamps are broker server time, so `server_utc_offset_seconds` must be configured from the broker specification; a wrong offset makes quotes look stale and blocks trading.
