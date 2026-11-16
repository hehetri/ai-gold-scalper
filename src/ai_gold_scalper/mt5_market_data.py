"""Optional read-only adapter for the official MetaTrader 5 Python package.

This module never submits, modifies, or closes orders. Install the optional
dependency on a compatible Windows machine with: pip install -e ".[mt5]".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from types import TracebackType
from typing import Any, Literal, Self

try:
    import MetaTrader5 as _mt5
except ImportError:  # Research and backtests must work without the terminal.
    _mt5 = None


class MT5UnavailableError(RuntimeError):
    """Raised when the MetaTrader 5 package or terminal is unavailable."""


class MT5ConnectionError(RuntimeError):
    """Raised when the terminal cannot be initialized or queried."""


class MT5DataError(RuntimeError):
    """Raised when market data or symbol metadata is invalid."""


@dataclass(frozen=True)
class SymbolSnapshot:
    name: str
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_stops_level: int
    trade_freeze_level: int
    currency_base: str
    currency_profit: str
    currency_margin: str


@dataclass(frozen=True)
class AccountSnapshot:
    """Account figures needed by risk checks. Deliberately excludes login/server."""

    currency: str
    balance: float
    equity: float
    margin_free: float
    trade_allowed: bool


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    time_msc: int
    tick_time_utc: datetime  # broker tick time converted to UTC
    received_at_utc: datetime  # local clock when the quote was read

    @property
    def spread(self) -> float:
        return self.ask - self.bid


class MT5MarketData:
    """Read-only MT5 connection and market-data access.

    MT5 reports tick and bar times in *broker server time* encoded as epoch
    seconds. ``server_utc_offset_seconds`` (server time minus UTC) must be set
    from the broker's specification; it is never guessed. With a wrong offset
    quotes look stale or future-dated and are rejected (fail closed).
    """

    def __init__(self, terminal: Any = None, *, server_utc_offset_seconds: int) -> None:
        if type(server_utc_offset_seconds) is not int:
            raise ValueError("server_utc_offset_seconds must be an integer from the broker spec")
        self._terminal = terminal if terminal is not None else _mt5
        self._connected = False
        self._server_offset = timedelta(seconds=server_utc_offset_seconds)

    def _to_utc(self, server_epoch_seconds: float) -> datetime:
        return datetime.fromtimestamp(server_epoch_seconds, tz=UTC) - self._server_offset

    def connect(self, **initialize_options: Any) -> None:
        if self._terminal is None:
            raise MT5UnavailableError(
                "MetaTrader5 package is not installed. Install the optional [mt5] extra "
                "on a compatible Windows machine with an MT5 terminal."
            )
        if not self._terminal.initialize(**initialize_options):
            error = self._terminal.last_error()
            raise MT5ConnectionError(f"MT5 initialize failed: {error}")
        self._connected = True

    def disconnect(self) -> None:
        if self._connected:
            self._terminal.shutdown()
            self._connected = False

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.disconnect()

    def _require_connection(self) -> None:
        if not self._connected:
            raise MT5ConnectionError("MT5 is not connected. Call connect() first.")

    def resolve_symbol(self, requested: str = "XAUUSD") -> str:
        self._require_connection()
        if not requested or not requested.strip():
            raise ValueError("requested symbol must not be empty")
        symbols = self._terminal.symbols_get()
        if symbols is None:
            raise MT5DataError(f"Could not list MT5 symbols: {self._terminal.last_error()}")
        names = [item.name for item in symbols]
        if requested in names:
            chosen = requested
        else:
            matches = [name for name in names if name.upper().startswith(requested.upper())]
            if len(matches) != 1:
                raise MT5DataError(
                    f"Could not resolve {requested!r} unambiguously. "
                    f"Candidates: {matches[:20]}"
                )
            chosen = matches[0]
        if not self._terminal.symbol_select(chosen, True):
            raise MT5DataError(
                f"Could not select symbol {chosen!r}: {self._terminal.last_error()}"
            )
        return chosen

    def symbol_snapshot(self, symbol: str) -> SymbolSnapshot:
        self._require_connection()
        info = self._terminal.symbol_info(symbol)
        if info is None:
            raise MT5DataError(f"symbol_info({symbol!r}) failed: {self._terminal.last_error()}")
        required_positive = (
            "point", "trade_tick_size", "trade_tick_value", "trade_contract_size",
            "volume_min", "volume_max", "volume_step",
        )
        for field in required_positive:
            value = getattr(info, field, None)
            if value is None or not isfinite(float(value)) or value <= 0:
                raise MT5DataError(f"Invalid broker symbol metadata: {field}={value!r}")
        return SymbolSnapshot(
            name=symbol,
            digits=int(info.digits),
            point=float(info.point),
            trade_tick_size=float(info.trade_tick_size),
            trade_tick_value=float(info.trade_tick_value),
            contract_size=float(info.trade_contract_size),
            volume_min=float(info.volume_min),
            volume_max=float(info.volume_max),
            volume_step=float(info.volume_step),
            trade_stops_level=int(info.trade_stops_level),
            trade_freeze_level=int(info.trade_freeze_level),
            currency_base=str(getattr(info, "currency_base", "")),
            currency_profit=str(getattr(info, "currency_profit", "")),
            currency_margin=str(getattr(info, "currency_margin", "")),
        )

    def quote(self, symbol: str, max_age_seconds: float = 3.0) -> Quote:
        self._require_connection()
        if not isfinite(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be finite and positive")
        tick = self._terminal.symbol_info_tick(symbol)
        if tick is None:
            raise MT5DataError(
                f"symbol_info_tick({symbol!r}) failed: {self._terminal.last_error()}"
            )
        if not (isfinite(tick.bid) and isfinite(tick.ask) and 0 < tick.bid <= tick.ask):
            raise MT5DataError(f"Invalid bid/ask for {symbol}: bid={tick.bid}, ask={tick.ask}")
        time_msc = int(getattr(tick, "time_msc", 0) or int(tick.time) * 1000)
        tick_time = self._to_utc(time_msc / 1000)
        now = datetime.now(UTC)
        age = (now - tick_time).total_seconds()
        if age < -1 or age > max_age_seconds:
            raise MT5DataError(f"Stale/future quote for {symbol}: age={age:.3f}s")
        return Quote(
            symbol=symbol,
            bid=float(tick.bid),
            ask=float(tick.ask),
            time_msc=time_msc,
            tick_time_utc=tick_time,
            received_at_utc=now,
        )

    def account_snapshot(self) -> AccountSnapshot:
        self._require_connection()
        info = self._terminal.account_info()
        if info is None:
            raise MT5DataError(f"account_info() failed: {self._terminal.last_error()}")
        balance, equity, margin_free = (
            float(info.balance), float(info.equity), float(info.margin_free)
        )
        if not all(isfinite(v) for v in (balance, equity, margin_free)) or equity <= 0:
            raise MT5DataError("Invalid account balance/equity/free margin")
        return AccountSnapshot(
            currency=str(info.currency),
            balance=balance,
            equity=equity,
            margin_free=margin_free,
            trade_allowed=bool(info.trade_allowed),
        )

    def _order_type(self, side: Literal["long", "short"]) -> int:
        if side not in ("long", "short"):
            raise ValueError("side must be 'long' or 'short'")
        name = "ORDER_TYPE_BUY" if side == "long" else "ORDER_TYPE_SELL"
        return int(getattr(self._terminal, name))

    def estimate_stop_loss(
        self, symbol: str, side: Literal["long", "short"], volume: float,
        entry_price: float, stop_price: float,
    ) -> float:
        """Broker-computed cash loss (positive) at the stop via order_calc_profit.

        A pure calculation in account currency: no order is created or sent.
        """
        self._require_connection()
        profit = self._terminal.order_calc_profit(
            self._order_type(side), symbol, volume, entry_price, stop_price
        )
        if profit is None or not isfinite(float(profit)) or float(profit) >= 0:
            raise MT5DataError(
                f"order_calc_profit gave no valid loss for {symbol}: {profit!r} "
                f"{self._terminal.last_error()}"
            )
        return -float(profit)

    def estimate_margin(
        self, symbol: str, side: Literal["long", "short"], volume: float, price: float
    ) -> float:
        """Broker-computed required margin via order_calc_margin (no order is sent)."""
        self._require_connection()
        margin = self._terminal.order_calc_margin(self._order_type(side), symbol, volume, price)
        if margin is None or not isfinite(float(margin)) or float(margin) <= 0:
            raise MT5DataError(
                f"order_calc_margin failed for {symbol}: {margin!r} {self._terminal.last_error()}"
            )
        return float(margin)

    def rates(self, symbol: str, timeframe: int, count: int) -> list[dict[str, Any]]:
        self._require_connection()
        if count < 2:
            raise ValueError("count must be at least 2")
        rates = self._terminal.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            raise MT5DataError(f"Could not fetch rates for {symbol}: {self._terminal.last_error()}")
        if len(rates) == 0:
            raise MT5DataError(f"No rates returned for {symbol}")
        # MT5 position 0 is the currently forming candle. Exclude it so callers
        # cannot accidentally treat an unfinished bar as a confirmed signal.
        closed = rates[:-1]
        return [
            {
                "time": self._to_utc(int(row["time"])),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": int(row["tick_volume"]),
                "spread": int(row["spread"]),
                "real_volume": int(row["real_volume"]),
            }
            for row in closed
        ]
