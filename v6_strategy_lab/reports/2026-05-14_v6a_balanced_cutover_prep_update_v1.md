# V6-A Balanced Challenger Cutover Prep Update v1

- Date: `2026-05-14`
- Scope: advance `balanced challenger` from research winner into cutover-ready evidence without touching the current live `ATTACK_EQUAL_REPLAY` sleeve

## One-Line Read

`Balanced challenger` 的研究优势还在，但 `cutover-ready` 还差最后两步：

1. `fresh replay` 不能再停在 `2026-05-05`
2. `single-candidate preview` 需要成功走完 quotes/account/orders 路径

## What Was Completed Today

### 1. Fresh replay re-run

- Command:

```bash
python3 v6a_core_deterministic_replay.py \
  --config v6_strategy_lab/configs/v6a_core_replay_bridge_v1.json \
  --tag 20260514_bridge_refresh_v1
```

- New artifacts:
  - `backtest_results/v6a_core_replay/v6a_core_replay_summary_20260514_bridge_refresh_v1_v6a_core_balanced.csv`
  - `backtest_results/v6a_core_replay/v6a_core_replay_composite_20260514_bridge_refresh_v1_v6a_core_balanced.csv`

- Result:
  - balanced challenger metrics stayed strong
  - `latest_date` still equals `2026-05-05`

- Meaning:
  - this was a valid replay refresh attempt
  - the blocker is no longer “we forgot to rerun replay”
  - the blocker is now clearly `historical input freshness`

### 2. Guarded-runner policy for balanced challenger

- New config:
  - `v6_strategy_lab/configs/v6a_balanced_challenger_guarded_runner_policy_v1.json`

- Purpose:
  - point guarded-runner at the single-candidate balanced replay artifacts
  - keep current `V6-A ATTACK_EQUAL_REPLAY` managed state only for netting and migration evidence
  - avoid touching the live ATTACK pilot itself

### 3. Migration diff builder

- New script:
  - `v6a_cutover_migration_diff.py`

- Best current artifact:
  - `backtest_results/v6a_cutover/v6a_cutover_migration_diff_20260514_balanced_cutover_v2.md`

- Snapshot source:
  - reused the successful real-account snapshot captured at `2026-05-14T10:07:19`
  - fallback was necessary because direct OpenD preview calls later in the session timed out

## Current Migration Diff

### Ownership Transfer + Incremental Buy

- `US.AMZN`: managed `4` -> target `6` => transfer `4`, buy `2`
- `US.AVGO`: managed `2` -> target `3` => transfer `2`, buy `1`

### Buy Only

- `US.NVDA`: managed `0` -> target `7` => buy `7`

### Sell Only

- `US.BIL`: `6` -> `0`
- `US.GLD`: `1` -> `0`
- `US.GOOGL`: `2` -> `0`

## Preview Status

### What passed

- replay artifacts exist
- single-candidate policy now exists
- migration diff is now explicit, not hand-waved

### What did not pass

- guarded-runner preview path still saw `quote/account timeout`
- even without timeout, `signal_freshness_gate` would still fail because `signal_date=2026-05-05`

## Practical Conclusion

今天的结果不是 `GO_CUTOVER`，也不是推翻 `balanced challenger`。

更准确的状态是：

`research winner` -> `implementation path partially wired` -> `still blocked by freshness + preview stability`

## Next Actions

1. Refresh the replay input chain so `latest_date` reaches current trading date.
2. Re-run balanced single-candidate preview until `quotes/account/orders` are all readable.
3. Keep current live ATTACK pilot unchanged while collecting the rest of the cutover pack.
