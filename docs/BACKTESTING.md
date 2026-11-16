# Backtesting protocol

Validate source, timezone, timestamps, gaps, duplicates, outliers, symbol mapping and candle construction. Preserve raw data and document transformations.

Model variable bid/ask spread, commissions, slippage, latency, rejected/partial fills and realistic stop/limit behavior. Use chronological development, validation and untouched out-of-sample splits; walk-forward where practical. Never randomly shuffle time series. Fit ML preprocessing only on training windows.

Report net P&L after costs, trade count, exposure, win rate, average win/loss, expectancy, profit factor, max drawdown/duration, worst losing streak, and performance by session/regime/side. Compare with baseline and stress costs/parameters. Do not select only by historical profit. Backtests do not guarantee future performance.

## Current harness

`backtest.run_backtest` replays mid-price OHLC bars with a constant spread, one position at a time. Stops win same-bar collisions, gaps through the stop fill at the bar open, targets get no price improvement, and `max_holding_bars` forces a time exit. It has no partial fills, latency, swaps or variable spread. Feed its net trade P/L to `risk_analysis.analyze_trades` for the risk report.
