# MT5 order lifecycle

No execution adapter exists. Building one is a separate, owner-approved
milestone; this file is the specification it must meet.

Before sending: terminal connected, account trade permission, symbol trade
mode and session, fresh quote, filling mode, margin, and an approved
`ReviewDecision` from `DualAgentReview` for exactly this proposal. Read digits,
point, tick size/value, contract size, volume min/max/step, stops level and
freeze level at runtime.

States: CREATED, VALIDATED, SUBMITTED, ACCEPTED, PARTIALLY_FILLED, FILLED,
REJECTED, CANCELLED, UNKNOWN. Persist the intent and broker IDs before
submission. Inspect every result code.

UNKNOWN after a timeout or disconnect: reconnect and reconcile orders, deals
and positions by magic number and intent ID before doing anything else. Never
blindly resubmit. Log result codes; never log credentials or account
identifiers.

Kill switch: persisted, checked before every submission, and with documented
behaviour for positions already open.
