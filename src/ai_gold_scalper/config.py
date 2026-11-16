"""Typed, validated settings. Loading a config can never enable live trading."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .risk import RiskLimits


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppSettings(_Strict):
    mode: Literal["backtest", "paper", "demo", "live"] = "backtest"
    timezone: str = "UTC"


class MarketSettings(_Strict):
    requested_symbol: str = Field(min_length=1)
    context_timeframe: Literal["M5"] = "M5"
    entry_timeframe: Literal["M1"] = "M1"
    max_quote_age_seconds: float = Field(gt=0)
    signal_max_age_seconds: float = Field(gt=0)
    # Broker server time minus UTC. Must come from the broker; null blocks MT5 use.
    server_utc_offset_seconds: int | None = None


class StrategySettings(_Strict):
    use_closed_candles_only: Literal[True] = True
    ema_fast: int = Field(gt=0)
    ema_slow: int = Field(gt=0)
    ema_regime: int = Field(gt=0)
    rsi_period: int = Field(gt=0)
    atr_period: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> StrategySettings:
        if not self.ema_fast < self.ema_slow < self.ema_regime:
            raise ValueError("Require ema_fast < ema_slow < ema_regime")
        return self


class RiskSettings(_Strict):
    enabled: Literal[True] = True  # the risk gate cannot be switched off
    max_risk_per_trade_pct: float = Field(gt=0, le=1.0)
    max_daily_loss_pct: float = Field(gt=0, le=5.0)
    max_total_drawdown_pct: float = Field(gt=0, le=20.0)
    max_consecutive_losses: int = Field(ge=1)
    max_trades_per_day: int = Field(ge=1)
    max_open_positions: int = Field(ge=1)
    min_reward_risk: float = Field(gt=0)
    max_margin_usage_pct: float = Field(gt=0, le=100)
    # Price units, from the broker's real spread behaviour. No universal default.
    max_spread_price: float | None = Field(default=None, gt=0)


class ExecutionSettings(_Strict):
    allow_new_orders: bool = False
    allow_live_trading: bool = False
    magic_number: int = Field(gt=0)


class Settings(_Strict):
    app: AppSettings
    market: MarketSettings
    strategy: StrategySettings
    risk: RiskSettings
    execution: ExecutionSettings

    @model_validator(mode="after")
    def _no_live(self) -> Settings:
        if self.app.mode == "live" or self.execution.allow_live_trading:
            raise ValueError(
                "Live trading is not implemented or approved; use backtest, paper or demo"
            )
        if self.execution.allow_new_orders and self.app.mode != "demo":
            raise ValueError("allow_new_orders is only meaningful in demo mode")
        return self

    def risk_limits(self) -> RiskLimits:
        if self.risk.max_spread_price is None:
            raise ValueError("risk.max_spread_price must be set from the broker specification")
        return RiskLimits(
            max_spread_price=self.risk.max_spread_price,
            max_risk_per_trade_pct=self.risk.max_risk_per_trade_pct,
            max_daily_loss_pct=self.risk.max_daily_loss_pct,
            max_total_drawdown_pct=self.risk.max_total_drawdown_pct,
            max_consecutive_losses=self.risk.max_consecutive_losses,
            max_trades_per_day=self.risk.max_trades_per_day,
            max_open_positions=self.risk.max_open_positions,
            max_quote_age_seconds=self.market.max_quote_age_seconds,
            min_reward_risk=self.risk.min_reward_risk,
            max_margin_usage_pct=self.risk.max_margin_usage_pct,
        )


def load_settings(path: str | Path) -> Settings:
    """Load and validate a YAML settings file; raises on any unknown or unsafe value."""
    with Path(path).open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("Settings file must contain a mapping")
    return Settings.model_validate(raw)
