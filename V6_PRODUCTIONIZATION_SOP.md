# V6 Productionization SOP

- Created: 2026-05-11
- Scope: V6-A SIM-first closed loop, small real pilot readiness, V6-B research pause, guarded runner, reporting, and promotion rules.

## Core Principle

V6 already has strategy-level exits through target-weight changes, momentum decay, defensive switching, and rebalance logic. The missing piece is not a new discretionary stop-loss rule. The missing piece is a production execution layer that turns target weights into auditable orders.

## System Split

| Component | Role | Current Status |
| --- | --- | --- |
| `V6-A` | Mature baseline: fixed AI/mega momentum pool | SIM-first closed loop is active; real pilot waits for manual command |
| `V6-B` | Dynamic universe generator / Radar validation sleeve | Research/backtest first; SIM paused until strategy is complete |
| `V6 Engine` | Classic momentum, risk-on/off, defensive switch, rebalance | Keep stable; do not tune from short-term noise |
| `Allocator` | Capital/risk allocator between V6 sleeves | Rule-based; V6-B weight remains 0 until evidence passes |
| `Reporting` | Weekly/monthly/quarterly status and reminders | Implemented via `v6_reporting.py` |

## V6-A Guarded Runner

Policy:

```text
v6_strategy_lab/configs/v6a_guarded_runner_policy_v1.json
```

Run plan-only:

```bash
python3 v6a_guarded_runner.py --tag v6a_plan_only_YYYYMMDD
```

The guarded runner performs:

1. Generate live order preview.
2. Refresh quotes and account snapshot through Futu OpenD.
3. Run release gate.
4. Check blockers: gate failure, missing orders, order value invalid, quote/account warnings, notional limit breach.
5. Write auditable JSON/Markdown outputs.
6. Stop before real orders unless explicit execution flags are present.

Real execution requires all of the following:

```bash
python3 v6a_guarded_runner.py \
  --tag v6a_real_pilot_YYYYMMDD \
  --execute-real \
  --confirm EXECUTE_V6A_REAL_5000
```

Default output:

```text
backtest_results/v6a_guarded_runner/latest_run.json
backtest_results/v6a_guarded_runner/latest_run.md
```

## V6-A SIM-First Loop

V6-A must prove the full execution loop in Futu SIM before real pilot:

```bash
python3 attack_engine_sim_executor.py \
  --tag v6a_sim_plan_YYYYMMDD \
  --strategy-capital 5000 \
  --max-gross 1.0 \
  --max-order-value 5000 \
  --net-managed-positions \
  --managed-positions-state backtest_results/v6a_state/v6a_managed_positions_sim_19005590.json
```

Execute in SIM:

```bash
python3 attack_engine_sim_executor.py \
  --tag v6a_sim_exec_YYYYMMDD \
  --strategy-capital 5000 \
  --max-gross 1.0 \
  --max-order-value 5000 \
  --net-managed-positions \
  --managed-positions-state backtest_results/v6a_state/v6a_managed_positions_sim_19005590.json \
  --update-managed-state \
  --execute-sim
```

Reconcile SIM state:

```bash
python3 v6a_sim_reconciliation.py --tag v6a_sim_exec_YYYYMMDD
```

SIM boundary rules:

- V6-A SIM uses `backtest_results/v6a_state/v6a_managed_positions_sim_19005590.json`.
- Old mixed holdings in the Futu SIM account are ignored.
- V6-A SIM may only sell quantities recorded in V6-A SIM managed state.
- Submitted SIM orders become pending first; only filled orders enter managed positions after reconciliation.
- After reconciliation, rerunning plan-only should generate `HOLD` or true rebalance orders, not duplicate buys.

## V6-A Exit Mechanism

V6-A exits through target portfolio changes:

- If a ticker drops out of the selected target weights, target quantity becomes 0 and the next rebalance should generate a sell order.
- If a ticker weight falls, the next rebalance should generate a partial sell.
- If risk-off/defensive mode is selected, exposure shifts toward defensive assets such as `BIL`, `GLD`, or cash.
- The runner must not invent discretionary per-stock take-profit/stop-loss rules unless a separate challenger proves them superior.

This is intentional. V6-A is the historical `ATTACK_EQUAL_REPLAY` strategy that produced the accepted backtest results. Its exit logic is signal/weight/risk-regime based, not fixed single-stock stop-profit/stop-loss.

## Managed State Boundary

V6-A must maintain a separate managed position state:

```text
backtest_results/v6a_state/v6a_managed_positions_real_281756481449956811.json
backtest_results/v6a_state/v6a_managed_positions_sim_19005590.json
```

Rules:

- V6-A may only sell shares recorded in this managed state.
- V6-A must not net or sell unrelated long-term/value-investing holdings in the same Futu account.
- If a ticker exists both as a long-term holding and as a V6 holding, V6 can only manage the quantity recorded in V6 state.
- If state strategy name mismatches `V6-A ATTACK_EQUAL_REPLAY`, execution must block.
- If a sell order exceeds managed quantity, execution must block.
- Real order submissions are recorded as pending orders first.
- Filled orders are promoted into managed positions only after reconciliation.

Reconciliation:

```bash
python3 v6a_real_reconciliation.py
```

This queries real Futu orders and converts filled V6 pending orders into V6 managed positions. It does not infer V6 positions from unrelated account holdings.

## V6-B Simulation

Current rule: V6-B does not advance further in SIM until the Radar/universe strategy is backtested and optimized. V6-B's purpose is to become the dynamic universe source for future V6, not to contaminate the validated V6-A baseline.

Policy:

```text
v6_strategy_lab/configs/v6b_sim_runner_policy_v1.json
```

Plan-only:

```bash
python3 v6b_live_forward_sim_executor.py --tag v6b_plan_YYYYMMDD
```

Execute in Futu SIM only:

```bash
python3 v6b_live_forward_sim_executor.py --tag v6b_sim_YYYYMMDD --execute-sim
```

V6-B cannot be promoted to real money until:

- Point-in-time universe audit passes.
- Historical synthetic Radar generator backtest passes.
- OOS validation passes.
- V6-A comparison passes.
- Combined V6-A + V6-B sleeve test improves risk-adjusted return.
- Allocator grants non-zero weight.
- Manual CIO confirmation is recorded.

## Reporting

Generate report:

```bash
python3 v6_reporting.py --period weekly
```

Send email:

```bash
python3 v6_reporting.py --period weekly --send-email
```

Reports are read-only and cannot trigger orders.

## Promotion Ladder

1. `PLAN_ONLY`: no order execution.
2. `SIMULATE`: Futu simulation only.
3. `REAL_PILOT_5K_MANUAL`: real account, small capital, manual confirmation.
4. `REAL_PILOT_AUTO_REVIEWED`: small capital, scheduled runner, strict kill switch.
5. `REAL_SCALED`: only after several weeks/months of clean execution and strategy evidence.

## Current Decision

As of 2026-05-11:

- V6-A SIM-first loop has executed and reconciled successfully through managed state.
- V6-A can proceed to small real pilot only through `v6a_guarded_runner.py`, after explicit manual command.
- V6-B remains research/backtest first; SIM expansion is paused.
- No V6 auto real runner is enabled.
- No launchctl production task should be installed until V6-A SIM runs remain stable and real pilot rules are confirmed.
