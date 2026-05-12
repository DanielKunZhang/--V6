# V6 Automation Preflight Gate Spec

- Created: 2026-05-12
- Owner split: GPT defines gate policy and failure behavior; Claude implements code and tests.
- Implementation status: spec only, no production code change.

## Purpose

Define the minimum gate required before V6-A can move from manual real pilot to small automatic execution.

The gate must prevent unattended trading when operational state is uncertain.

## Principle

Automation is allowed only when:

- OpenD is reachable.
- The strategy has a fresh plan.
- Managed state is valid.
- There are no unresolved pending orders.
- Account cash is sufficient.
- Expected order value and slippage risk are within policy.
- Kill switch is off.

If any critical check fails, the system must report and stop before order placement.

## Recommended Files

Config:

```text
v6_strategy_lab/configs/v6_automation_preflight_policy_v1.json
```

Script:

```text
v6_automation_preflight_gate.py
```

Outputs:

```text
backtest_results/v6_automation_preflight/v6_automation_preflight_<tag>.json
backtest_results/v6_automation_preflight/v6_automation_preflight_<tag>.md
```

## Kill Switch

Required config:

```json
{
  "kill_switch": {
    "enabled": true,
    "reason": "manual_review",
    "updated_at": "2026-05-12",
    "updated_by": "user"
  }
}
```

Default before automation:

```text
kill_switch.enabled = true
```

Real automatic execution is allowed only when:

```text
kill_switch.enabled = false
```

Manual pilot commands may still run through explicit user confirmation, but the report must show kill switch state.

## Gate Checks

### 1. OpenD / Futu connectivity

Check:

- quote context reachable
- trade context reachable
- account query succeeds
- quote query succeeds for target symbols

Failure behavior:

```text
BLOCK_AUTO_EXECUTION
send alert
do not place orders
retry next scheduled cycle
```

### 2. Managed state validity

Check:

- state file exists
- `strategy == V6-A ATTACK_EQUAL_REPLAY`
- `positions` is a dict
- `pending_orders` is a list
- no negative long position quantity
- all symbols use normalized `US.` ticker format

Failure behavior:

```text
BLOCK_AUTO_EXECUTION
require manual state repair
```

### 3. Pending orders

Check:

- `pending_orders` count is 0 before new automatic order placement
- if pending exists, query latest order status
- if final status, reconciliation should clear it first
- if still active, block

Failure behavior:

```text
BLOCK_AUTO_EXECUTION
do not submit duplicate orders
```

### 4. Account cash / buying power

Check:

- available cash >= total buy notional + cash buffer
- configurable cash buffer, default `100 USD`
- SELL orders can still be suggested, but automatic partial execution rules must be explicit

Initial policy:

```text
If buys cannot be fully funded, block all automatic execution.
Manual review may later decide whether to execute sells only.
```

Reason: partial execution can unintentionally change exposure.

### 5. Order size limits

Check:

- total executable notional <= max total notional
- single order value <= max order value
- no order below min order value unless it is a full exit of an existing V6 managed position

Default pilot values:

```text
max_total_notional_usd = 5000
max_order_value_usd = 5000
min_order_value_usd = 25
```

### 6. Slippage guard

Before execution:

- compare quote bid/ask spread to mid
- block if spread exceeds threshold

Suggested thresholds:

```text
max_spread_pct_core = 0.30%
max_spread_pct_defensive_etf = 0.10%
```

After execution:

- reconciliation computes slippage vs preview price
- if slippage exceeds threshold, mark warning in daily report
- do not auto-reverse trade

Suggested post-trade warning thresholds:

```text
warning_slippage_pct = 0.50%
critical_slippage_pct = 1.00%
```

### 7. Release gate freshness

Check:

- latest release gate exists
- release gate result is PASS
- strategy signal age <= policy max
- current preview generated after latest reconciliation

Failure behavior:

```text
BLOCK_AUTO_EXECUTION
```

### 8. Trading session policy

Initial rule:

```text
Automatic execution only during regular US market hours.
No pre-market or after-hours automatic orders.
```

Manual pilot may still be considered separately if the user explicitly confirms.

## Four Required Scenario Outcomes

| Scenario | Trigger | Required behavior |
| --- | --- | --- |
| OpenD down | quote/trade/account query fails | block execution, send alert, retry next cycle |
| Unfilled order | pending order remains active | block new orders, report pending, require manual review |
| Insufficient funds | buy notional exceeds available cash buffer | block all auto execution, report funding gap |
| Excess slippage/spread | spread or fill slippage exceeds threshold | pre-trade block for spread; post-trade warning for fill slippage |

## Output Schema

JSON output must include:

```json
{
  "tag": "...",
  "generated_at": "...",
  "decision": "PASS" ,
  "auto_execution_allowed": false,
  "checks": [
    {
      "name": "managed_state_valid",
      "status": "PASS",
      "severity": "BLOCKER",
      "detail": ""
    }
  ],
  "blockers": [],
  "warnings": [],
  "artifacts": {}
}
```

Decision values:

```text
PASS
WARN
BLOCK
ERROR
```

Severity values:

```text
INFO
WARN
BLOCKER
```

## Test Requirements

Claude should add focused tests or smoke fixtures for:

- kill switch on blocks automation
- malformed managed state blocks
- pending order blocks
- insufficient cash blocks
- high spread blocks
- clean fixture passes

If the repo does not have a test framework for these scripts, create a deterministic smoke command using local fixture JSON files.

## Integration Point

Future automatic runner must call this gate before placing any real order.

Initial integration recommendation:

```text
v6_auto_runner.py
  1. reconciliation
  2. plan-only preview
  3. automation_preflight_gate
  4. execute only if gate PASS and kill_switch off
  5. reconciliation
  6. report
```

Current manual pilot runner may reference the gate in reports, but should not be blocked by kill switch if the user explicitly runs manual execution with the confirmation phrase.

## Acceptance Criteria

Spec implementation is complete when:

- all four failure scenarios are represented in code/config
- output JSON clearly states `auto_execution_allowed`
- a human can read the markdown and know exactly why execution is allowed or blocked
- no real order can be placed by a future automatic runner without a PASS
- kill switch defaults to blocking automation

## Boundaries

- Do not enable automatic real trading in this task.
- Do not alter V6-A strategy logic.
- Do not change managed positions.
- Do not execute real orders.
- Do not silently downgrade blockers to warnings.

## Claude Deliverable

Claude should implement the gate as a standalone script first. Integration into any automatic trading runner must be a separate task after GPT/user review.
