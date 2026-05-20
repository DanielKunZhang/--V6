# Risk Control Status

The old Iron Condor risk-control document is obsolete because the IC automation chain has been removed.

Current risk-control sources:

- `CENTRAL_RISK_BOARD_SPEC.md`
- `V6_STRATEGY_LAB.md`
- `v6_strategy_lab/reports/2026-05-18_v6_stale_data_risk_exit_policy_v1.md`
- `SYSTEM_OVERVIEW.html`

Current hard rules:

- No unattended real trading for V6.
- V6-A remains a small real manual pilot.
- V6AB remains paper simulation until fills, reconciliation, and forward evidence justify any later decision.
- Stale data mode blocks BUY / ADD / ROTATE_IN and only allows risk-exit review.
- Deleted Iron Condor scripts must not be treated as active controls.
