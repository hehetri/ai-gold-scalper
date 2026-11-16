import math
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ai_gold_scalper.mt5_market_data import (
    MT5ConnectionError,
    MT5DataError,
    MT5MarketData,
)


class FakeTerminal:
    TIMEFRAME_M1 = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, server_offset=0, bid=2300.10, profit=-20.0, margin=230.0):
        self.initialized = False
        self.selected = []
        self.server_offset = server_offset
        self.bid = bid
        self.profit = profit
        self.margin = margin
        self.calc_calls = []

    def account_info(self):
        return SimpleNamespace(currency="USD", balance=10_000.0, equity=9_990.0,
                               margin_free=9_500.0, trade_allowed=True, login=123)

    def order_calc_profit(self, action, symbol, volume, price_open, price_close):
        self.calc_calls.append((action, symbol, volume, price_open, price_close))
        return self.profit

    def order_calc_margin(self, action, symbol, volume, price):
        return self.margin

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
        now = int(datetime.now(UTC).timestamp()) + self.server_offset
        return SimpleNamespace(bid=self.bid, ask=2300.20, time=now, time_msc=now * 1000)

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
    assert bars[-1]["time"].tzinfo == UTC
    adapter.disconnect()


def test_disconnect_is_safe_when_not_connected():
    adapter = MT5MarketData(FakeTerminal())
    adapter.disconnect()


def connected(terminal=None, **kwargs):
    adapter = MT5MarketData(terminal or FakeTerminal(), **kwargs)
    adapter.connect()
    return adapter


def test_missing_package_fails_closed(monkeypatch):
    import ai_gold_scalper.mt5_market_data as module

    monkeypatch.setattr(module, "_mt5", None)
    with pytest.raises(module.MT5UnavailableError):
        MT5MarketData().connect()


def test_quote_honours_broker_server_offset():
    terminal = FakeTerminal(server_offset=7200)
    with pytest.raises(MT5DataError, match="Stale/future"):
        connected(terminal).quote("XAUUSD.a")
    quote = connected(terminal, server_utc_offset_seconds=7200).quote("XAUUSD.a")
    assert abs((quote.received_at_utc - quote.tick_time_utc).total_seconds()) < 3


@pytest.mark.parametrize("bid", [math.nan, 0.0, 2300.50])
def test_quote_rejects_invalid_bid(bid):
    with pytest.raises(MT5DataError, match="Invalid bid/ask"):
        connected(FakeTerminal(bid=bid)).quote("XAUUSD.a")


def test_ambiguous_symbol_is_rejected():
    terminal = FakeTerminal()
    terminal.symbols_get = lambda: [SimpleNamespace(name="XAUUSD.a"),
                                    SimpleNamespace(name="XAUUSD.b")]
    with pytest.raises(MT5DataError, match="unambiguously"):
        connected(terminal).resolve_symbol("XAUUSD")


def test_invalid_symbol_metadata_is_rejected():
    terminal = FakeTerminal()
    good = terminal.symbol_info("XAUUSD.a")
    good.trade_tick_value = 0.0
    terminal.symbol_info = lambda symbol: good
    with pytest.raises(MT5DataError, match="trade_tick_value"):
        connected(terminal).symbol_snapshot("XAUUSD.a")


def test_account_snapshot_excludes_identifiers():
    snapshot = connected().account_snapshot()
    assert snapshot.equity == 9_990.0
    assert snapshot.margin_free == 9_500.0
    assert not hasattr(snapshot, "login")


def test_estimate_stop_loss_uses_broker_calculation():
    terminal = FakeTerminal()
    loss = connected(terminal).estimate_stop_loss("XAUUSD.a", "long", 0.1, 2300.2, 2298.2)
    assert loss == 20.0
    assert terminal.calc_calls == [(0, "XAUUSD.a", 0.1, 2300.2, 2298.2)]
    connected(terminal).estimate_stop_loss("XAUUSD.a", "short", 0.1, 2300.0, 2302.0)
    assert terminal.calc_calls[-1][0] == 1


@pytest.mark.parametrize("profit", [None, 5.0, 0.0, math.nan])
def test_estimate_stop_loss_fails_closed(profit):
    with pytest.raises(MT5DataError):
        connected(FakeTerminal(profit=profit)).estimate_stop_loss(
            "XAUUSD.a", "long", 0.1, 2300.2, 2298.2
        )


def test_estimate_margin():
    assert connected().estimate_margin("XAUUSD.a", "long", 0.1, 2300.2) == 230.0
    with pytest.raises(MT5DataError):
        connected(FakeTerminal(margin=None)).estimate_margin("XAUUSD.a", "long", 0.1, 2300.2)


def test_adapter_exposes_no_order_submission():
    assert not [name for name in dir(MT5MarketData) if "send" in name or "order_check" in name]
