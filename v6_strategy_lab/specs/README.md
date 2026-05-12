# V6 Specs

This directory contains implementation-ready task specs. GPT owns the strategy/risk specification; Claude owns implementation and operational integration.

Current specs:

| Spec | Purpose | Implementation owner |
| --- | --- | --- |
| `2026-05-12_v6a_turnover_cost_audit_spec.md` | Measure V6-A turnover, cost sensitivity, and small-account feasibility | Claude |
| `2026-05-12_v6a_pilot_review_dashboard_spec.md` | Build the evidence pack for the 2026-05-26 V6-A pilot review | Claude |
| `2026-05-12_v6_automation_preflight_gate_spec.md` | Define the gate required before unattended V6 automation | Claude |

Rules:

- Specs do not authorize live trading.
- Implementation must not change V6-A engine logic unless a separate challenger process approves it.
- Claude should return generated report paths and caveats through `AI_COLLAB_EXPORT_FOR_GPT.md` for GPT review.
