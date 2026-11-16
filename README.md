# AI Gold Scalper

Research-first XAUUSD scalping system for MetaTrader 5, developed with a Claude Code project skill.

> **Safety:** backtest/research by default. Demo execution is a later milestone. Live order execution is disabled and requires explicit owner approval after all validation gates pass.

## Purpose
Build a modular, testable system using M5 for market context and M1 for entry timing as an initial hypothesis. Python handles research, data, backtesting and orchestration; MQL5 may be used for native execution where justified.

## Repository structure
- `.claude/skills/ai-gold-scalper/SKILL.md` — Claude Code skill.
- `.claude/skills/ai-gold-scalper/references/` — detailed workflows.
- `docs/` — architecture, strategy, risk, MT5 and validation specs.
- `src/ai_gold_scalper/` — Python package.
- `tests/` — deterministic tests.
- `config/settings.example.yaml` — safe example config.
- `CLAUDE.md` — repository-wide instructions.

## Setup
Use Python 3.11+ (64-bit Windows recommended for the official MT5 Python package):
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```
Install the optional MT5 dependency only on a compatible machine: `python -m pip install -e ".[dev,mt5]"`.

## Claude Code Desktop
Open this repository in Claude Code Desktop and run `/ai-gold-scalper`. The project skill is committed under `.claude/skills/`.

## Development status
- [x] Project specification and safety rules.
- [x] Claude Code skill and reference docs.
- [ ] MT5 market-data adapter.
- [ ] Broker-aware risk sizing and deterministic risk gate.
- [ ] Cost-aware historical backtester.
- [ ] Demo execution, reconciliation and monitoring.

No strategy performance or profitability is claimed. See `docs/RISK_MANAGEMENT.md` and `docs/BACKTESTING.md`.

Gold CFDs and leveraged trading carry substantial risk. This repository is software research, not investment advice.
