from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ai_gold_scalper.mt5_market_data import (
    MT5ConnectionError,
    MT5DataError,
    MT5MarketData,
)


class FakeTerminal:
    TIMEFRAME_M1 = 1

    def __init__(self):
        self.initialized = False
        self.selected = []

    def initialize(self, **kwargs):
        self.initialized = True
        return True

    def shutdown(self):
        self.initialized = False

    def last_error(self):
        return (0, "ok")

    def symbols_get(self):
        return [SimpleNamespace(name="EURUSD"), SimpleNamespace(name="XAUUSD.a")]

    def symbol_select(self, name, enabled):
        self.selected.append((name, enabled))
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(
            digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0,
            trade_contract_size=100.0, volume_min=0.01, volume_max=100.0,
            volume_step=0.01, trade_stops_level=0, trade_freeze_level=0,
            currency_base="XAU", currency_profit="USD", currency_margin="USD",
        )

    def symbol_info_tick(self, symbol):
        now = int(datetime.now(timezone.utc).timestamp())
        return SimpleNamespace(bid=2300.10, ask=2300.20, time=now, time_msc=now * 1000)

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        # Last row represents the still-forming candle and must be excluded.
        return [
            {"time": 100, "open": 1, "high": 2, "low": 0, "close": 1,
             "tick_volume": 10, "spread": 2, "real_volume": 0},
            {"time": 160, "open": 1, "high": 2, "low": 0, "close": 1,
             "tick_volume": 12, "spread": 2, "real_volume": 0},
            {"time": 220, "open": 1, "high": 2, "low": 0, "close": 1,
             "tick_volume": 15, "spread": 2, "real_volume": 0},
        ]


def test_requires_connection():
    adapter = MT5MarketData(FakeTerminal())
    with pytest.raises(MT5ConnectionError):
        adapter.resolve_symbol("XAUUSD")


def test_resolves_broker_suffix_and_selects_symbol():
    terminal = FakeTerminal()
    adapter = MT5MarketData(terminal)
    adapter.connect()
    assert adapter.resolve_symbol("XAUUSD") == "XAUUSD.a"
    assert terminal.selected == [("XAUUSD.a", True)]
    adapter.disconnect()


def test_symbol_snapshot_reads_broker_contract_properties():
    adapter = MT5MarketData(FakeTerminal())
    adapter.connect()
    snapshot = adapter.symbol_snapshot("XAUUSD.a")
    assert snapshot.digits == 2
    assert snapshot.volume_step == 0.01
    assert snapshot.contract_size == 100.0
    adapter.disconnect()


def test_quote_returns_bid_ask_and_spread():
    adapter = MT5MarketData(FakeTerminal())
    adapter.connect()
    quote = adapter.quote("XAUUSD.a")
    assert quote.ask > quote.bid
    assert quote.spread == pytest.approx(0.10)
    adapter.disconnect()


def test_rates_exclude_forming_candle():
    adapter = MT5MarketData(FakeTerminal())
    adapter.connect()
    bars = adapter.rates("XAUUSD.a", FakeTerminal.TIMEFRAME_M1, 3)
    assert len(bars) == 2
    assert bars[-1]["time"].tzinfo == timezone.utc
    adapter.disconnect()


def test_disconnect_is_safe_when_not_connected():
    adapter = MT5MarketData(FakeTerminal())
    adapter.disconnect()
