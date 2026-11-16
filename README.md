# AI Gold Scalper

Research-first XAUUSD scalping project for MetaTrader 5, with a Claude Code project skill.

> **Safety:** research/backtest by default. The market-data adapter is read-only. No live order execution is implemented or enabled. A strategy is not considered profitable without robust out-of-sample and demo forward validation.

## What is included

- Claude Code Skill: `.claude/skills/ai-gold-scalper/SKILL.md`.
- M5 directional context and M1 pullback-trigger baseline.
- Pure EMA/RSI indicators and OHLC validation.
- Optional read-only MetaTrader 5 adapter for symbol discovery, broker metadata, quotes and completed candles.
- Deterministic risk sizing and account-level veto checks.
- Simplified OHLC backtesting harness with spread, slippage and commission inputs.
- Unit tests and GitHub Actions test workflow.
- Design references for architecture, strategy, MT5, risk and backtesting.

## Requirements

- Python 3.11 or newer.
- For the official Python MT5 package: compatible 64-bit Windows, installed MetaTrader 5 desktop terminal and broker login. Research/backtests do not require MT5.

## Install

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install -e ".[dev]"
pytest
ruff check .
```

Optional MT5 integration (compatible Windows machine only):

```bash
python -m pip install -e ".[dev,mt5]"
```

Copy `config/settings.example.yaml` to a local settings file and adjust it only after checking the broker's actual symbol specification. Never commit credentials or account secrets.

## Use with Claude Code Desktop

1. Clone this repository.
2. Open the repository folder in Claude Code Desktop.
3. Confirm Claude Code recognizes the project instructions in `CLAUDE.md`.
4. Invoke the skill with `/ai-gold-scalper`.
5. Start with: "Leia o projeto, rode os testes e me diga o próximo milestone seguro."

The skill is installed at `.claude/skills/ai-gold-scalper/SKILL.md` and is scoped to this repository. For a personal/global installation, copy the skill folder into `~/.claude/skills/ai-gold-scalper/`.

## Current implementation status

- [x] Project specification, Claude Code skill and reference docs.
- [x] M5/M1 baseline strategy and indicators.
- [x] Read-only MT5 market-data adapter.
- [x] Deterministic position sizing and risk veto baseline.
- [x] Simplified OHLC backtest baseline.
- [x] Unit tests and CI workflow.
- [ ] Tick-accurate, broker-cost-aware backtesting and walk-forward reports.
- [ ] Persistent risk state, MT5 order execution state machine and reconciliation.
- [ ] Demo-only execution, monitoring and forward testing.
- [ ] Live readiness review (not enabled by default).

## Important limitations

The local risk sizing calculation is a baseline and must be cross-checked with MT5's broker-specific profit calculation, especially for account-currency conversion and asymmetric tick values. The OHLC backtester is deliberately simplified; same-bar stop/target collisions are resolved conservatively, but it is not a substitute for tick-level simulation. No trading performance is claimed.

Gold CFDs and leveraged trading carry substantial risk. This repository is software research, not investment advice.
