# Backtest checklist

- Validate data source, timezone, gaps, duplicates and candle construction.
- Use chronological development, validation and untouched out-of-sample periods.
- Do not use future bars, unfinished candle values or random time-series shuffles.
- Model variable spread, commissions, slippage, latency, rejected/partial fills.
- Report net P&L, trade count, exposure, win rate, average win/loss, expectancy, profit factor, max drawdown/duration and worst losing streak.
- Segment by session, volatility regime and long/short.
- Stress costs and parameters; compare with a simple baseline.
- Never claim profitability based only on in-sample results.
