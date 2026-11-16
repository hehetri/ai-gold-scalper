# Backtesting protocol

Validate source, timezone, timestamps, gaps, duplicates, outliers, symbol mapping and candle construction. Preserve raw data and document transformations.

Model variable bid/ask spread, commissions, slippage, latency, rejected/partial fills and realistic stop/limit behavior. Use chronological development, validation and untouched out-of-sample splits; walk-forward where practical. Never randomly shuffle time series. Fit ML preprocessing only on training windows.

Report net P&L after costs, trade count, exposure, win rate, average win/loss, expectancy, profit factor, max drawdown/duration, worst losing streak, and performance by session/regime/side. Compare with baseline and stress costs/parameters. Do not select only by historical profit. Backtests do not guarantee future performance.
