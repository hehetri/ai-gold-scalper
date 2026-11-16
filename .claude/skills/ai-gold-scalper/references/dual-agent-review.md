# Dual-agent review

Two independent checks on every operation, at two levels. One reviewer is never
enough, and reviewers never see each other's conclusions before giving theirs.

## Runtime: `ai_gold_scalper.review`

```python
decision = DualAgentReview().review(proposal, context)
if not decision.approved:
    ...  # no trade; decision.reasons says why, decision.to_record() is the audit row
```

| Agent | Tests |
| --- | --- |
| `RiskAnalystAgent` | account gates (kill switch, daily loss, drawdown, streak, trade count, open positions, spread, quote age); reward/risk; volume within the risk-budget maximum from `calculate_position_size`; equity after a stop-out still above the daily and drawdown floors; margin usage |
| `ExecutionValidatorAgent` | mode allow-list (`live` and unknown modes vetoed; `demo` needs `allow_new_orders`); symbol metadata sanity; symbol match; finite numbers; timezone-aware timestamps; bid/ask sanity, spread and quote age recomputed from the raw quote; risk-state spread consistent with the quote; signal bar closed and not expired; stop/entry/target geometry; entry near the executable quote; prices on the tick grid; volume on the step grid and within min/max; broker stops/freeze distance; its own stop-out loss calculation, cross-checked against the broker's `order_calc_profit` figure |

Properties to preserve:

- Approval is unanimous. The two core agents are created inside
  `DualAgentReview` and cannot be replaced, renamed away or removed;
  `extra_agents` can only add vetoes.
- Modes are allow-listed (`backtest`, `paper`, `demo`). Any other value is
  vetoed and treated as broker-connected, so it also needs broker data.
- Flags must be real booleans: `paused` anything but `False` blocks,
  `allow_new_orders` anything but `True` blocks.
- Projected daily-loss and drawdown floors use the worse of the local and
  broker loss figures; the tolerance between them is capped at 10%.
- Stops/freeze distance is measured from both the entry and the closing-side
  quote (bid for a long, ask for a short), in decimal arithmetic.
- An exception inside an agent is a veto.
- A verdict marked approved that still carries reasons does not approve.
- The validator does not call the sizing function the analyst uses.
- In `demo` mode the broker loss estimate and margin figures are mandatory.
- Every decision is logged as one JSON line (`event: trade_review`).
- An approval is not an order. Execution remains separately gated and absent.

## Development: project subagents

Defined in `.claude/agents/`:

- `gold-risk-auditor` - reads the diff for weakened limits, fail-open paths,
  forbidden sizing patterns and unsupported risk claims.
- `gold-operation-tester` - runs the suite and executes adversarial scenarios.

Launch both in parallel with the same brief: what changed, why, which files,
which commands you already ran. Do not include your own opinion of whether it
is correct, and do not forward one agent's output to the other.

Required scenarios for the tester when the operation path changed: valid long
and short approved; oversized volume; stale quote; crossed and wide spread;
unfinished and expired signal bar; wrong-side stop; off-grid price and volume;
stop inside the stops level; missing broker loss or margin in demo; `live` mode.

Outcome table:

| Auditor | Tester | Result |
| --- | --- | --- |
| APPROVE | APPROVE | change may be reported as dual-verified |
| REJECT | any | blocked; fix, then re-run both |
| any | REJECT | blocked; fix, then re-run both |
| missing or no evidence | any | blocked; not dual-verified |
