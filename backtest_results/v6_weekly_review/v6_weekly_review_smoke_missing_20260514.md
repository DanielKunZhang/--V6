# Weekly V6 Review Board

- Generated: `2026-05-14T09:58:24`
- Week Ending: `2026-05-14`
- Review Decision: `Investigate / Continue manual pilot`

## 1. Outcome Snapshot

- V6-A pilot review: `CONTINUE_MANUAL_PILOT`
- Managed unrealized P/L: `-0.55%`
- Current top 3 concentration: `73.4%`
- Latest report action: `需要用户确认：检测到 armed 执行记录，复核订单和仓位。`

## 2. Process Integrity

- Managed state strategy: `V6-A ATTACK_EQUAL_REPLAY`
- Reconciliation unresolved issues: `0`
- Pending orders: `0`
- Preflight decision: `BLOCK`
- Preflight blockers: `kill_switch: Kill switch is ON (reason=manual_review, updated_at=2026-05-12). Set kill_switch.enabled=false in policy config to allow automation.; trading_session: Not in regular market hours: Tuesday 06:53 EDT (session 09:30–16:00 ET weekdays only)`

## 3. Exposure

- `US.AMZN`: weight `29.1%`, P/L `-1.01%`
- `US.AVGO`: weight `23.2%`, P/L `+0.25%`
- `US.GOOGL`: weight `21.0%`, P/L `-1.50%`

## 4. Research Signals

- V6-A raw top candidate: `mom120 top2 trend150 mkt200 dd10 rebal10` (promising_core_upgrade, AnnΔ `+11.3%`, SharpeΔ `+0.21`)
- V6-A balanced candidate: `mom60 top3 trend150 mkt200 dd10 rebal10` (promising_core_upgrade, AnnΔ `+7.8%`, SharpeΔ `+0.23`)
- V6-A robustness: `stable_neighbor_cluster` on `mom60 top3 trend150 mkt200 dd10 rebal10`
- V6-A cost re-audit: `candidate_survives_costs` on `mom60 top3 trend150 mkt200 dd10 rebal10`
- V6-B core_reaccel: `real_track_alpha` on `mom60 top2 trend120 mkt180 dd10 rebal10`
- V6-B turnaround: `real_track_alpha` on `mom60 top2 trend150 mkt200 dd08 rebal10`
- V6-B bottleneck: `return_only_track` on `mom120 top2 trend150 mkt200 dd10 rebal5`
- Missing opportunity review: `1 critical / 0 theme wakeups / 8 coverage gaps` as of `2026-05-08`
- Missing opportunity names: `US.COHR`
- Theme wakeups: `none`

## 5. Research Backlog

1. [P0] `execution_quality` Keep V6-A in manual pilot and collect more execution evidence
   - Reason: Pilot review remains CONTINUE_MANUAL_PILOT. System still in execution-validation phase.
   - Next: Continue manual pilot and reuse the same review board at the next weekly checkpoint.
2. [P1] `v6a_parameter_challenger` Build formal side-by-side board for the balanced V6-A challenger
   - Reason: Preferred candidate mom60 top3 trend150 mkt200 dd10 rebal10 shows Ann +7.8%, Sharpe +0.23, dd change -3.7% vs baseline. Robustness=stable_neighbor_cluster, cost_reaudit=candidate_survives_costs.
   - Next: Prepare baseline vs balanced challenger review board and implementation/replay plan.
3. [P1] `v6b_core_reaccel` Promote core_reaccel to formal V6-B challenger lane
   - Reason: Best core_reaccel overlay mom60 top2 trend120 mkt180 dd10 rebal10 still adds Ann +5.3% and Sharpe +0.08 vs same-parameter V6-A base-only.
   - Next: Keep core_reaccel ahead of other V6-B tracks and build the next validation board around it.
4. [P2] `v6b_turnaround` Keep turnaround as secondary research only
   - Reason: Turnaround still shows positive track increment, but only modestly (Ann +1.3%, Sharpe +0.03).
   - Next: Do not give allocator weight; only continue if new sparse-track evidence improves quality.
5. [P2] `v6b_bottleneck` Freeze bottleneck as a live promotion candidate
   - Reason: Bottleneck top row mom120 top2 trend150 mkt200 dd10 rebal5 does not pass true track-alpha test (track gate = return_only_track).
   - Next: Do not spend allocator attention here until universe quality or exits materially improve.
6. [P1] `radar_missing_opportunity` Review new missing-opportunity names before the next Radar universe refresh
   - Reason: Latest missing-opportunity review (2026-05-08) shows 1 critical misses and 0 theme wakeups. Names=US.COHR; themes=none.
   - Next: Decide whether to upgrade these names/themes into point-in-time research seed or explicitly document why they remain excluded.
7. [P2] `radar_coverage_gaps` Close Radar data and theme coverage gaps
   - Reason: Latest missing-opportunity review still has 8 coverage gaps and 2 active-but-weak names.
   - Next: Fetch or validate missing candidate data, then prune stale names or move them to explicit observe-only status.
8. [P3] `review_cadence` Keep weekly review cadence active
   - Reason: Latest report action is '需要用户确认：检测到 armed 执行记录，复核订单和仓位。'. Weekly review is now a formal governance step, not optional reflection.
   - Next: Run the weekly board again after the next full week of pilot data.
