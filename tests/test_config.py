from pathlib import Path

import pytest
import yaml

from ai_gold_scalper.config import load_settings

EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "settings.example.yaml"


def write(tmp_path, mutate):
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_example_config_is_valid_and_safe():
    settings = load_settings(EXAMPLE)
    assert settings.app.mode == "backtest"
    assert not settings.execution.allow_new_orders
    assert not settings.execution.allow_live_trading


def test_example_blocks_trading_until_spread_limit_is_set(tmp_path):
    with pytest.raises(ValueError, match="max_spread_price"):
        load_settings(EXAMPLE).risk_limits()
    path = write(tmp_path, lambda d: d["risk"].update(max_spread_price=0.4))
    limits = load_settings(path).risk_limits()
    assert limits.max_spread_price == 0.4
    assert limits.max_risk_per_trade_pct == 0.25
    assert limits.max_quote_age_seconds == 3


@pytest.mark.parametrize("mutate", [
    lambda d: d["app"].update(mode="live"),
    lambda d: d["execution"].update(allow_live_trading=True),
    lambda d: d["execution"].update(allow_new_orders=True),  # not in demo mode
    lambda d: d["risk"].update(enabled=False),
    lambda d: d["risk"].update(max_risk_per_trade_pct=5),
    lambda d: d["risk"].update(max_spread_price=-1),
    lambda d: d["risk"].update(max_risk_per_trade_pct=1.0, max_daily_loss_pct=0.5),
    lambda d: d["risk"].update(martingale_multiplier=2),
    lambda d: d["strategy"].update(use_closed_candles_only=False),
    lambda d: d["strategy"].update(ema_fast=50),
    lambda d: d.pop("risk"),
])
def test_unsafe_or_invalid_settings_are_rejected(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_settings(write(tmp_path, mutate))


def test_non_mapping_file_is_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)
