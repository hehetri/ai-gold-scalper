# Backtest checklist

Data
- Source, timezone (MT5 bars are broker server time), gaps, duplicates, outliers
  and candle construction validated. `validate_ohlc` rejects non-finite or
  inconsistent bars.

Method
- Chronological development, validation and untouched out-of-sample periods;
  walk-forward where practical. No random shuffling.
- Signals see only completed bars before the entry bar.
- Costs on both sides: spread, slippage, commission. Convert to account
  currency with broker `tick_value / tick_size` (`price_unit_value`).
- Know the harness limits (`backtest.run_backtest`): constant spread, mid-price
  bars, stop wins same-bar collisions, gaps through the stop fill at the open,
  no price improvement on targets, no partial fills, latency or swaps.

Report
- `risk_analysis.analyze_trades` output in full, including warnings.
- Segment by session, volatility regime and side. Compare with a simple
  baseline. Stress costs and parameters.
- State the sample size. Never claim profitability from in-sample results.
