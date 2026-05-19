# 2026-05-19 Disable Cash Alpha V3 Sim Emails

## Reason

The V3 simulation account emails are no longer needed and were still being delivered after the 2026 portfolio workflow shifted toward V6-A pilot, V6-B research, A-share Radar training, and the simplified 26 strategy plan.

## Disabled LaunchAgents

- `com.cashalpha.v3.smalltrack.sim.daily_report`
- `com.cashalpha.v3.smalltrack.sim.weekly_report`
- `com.cashalpha.v3.smalltrack.sim.guard`
- `com.cashalpha.v3.largetrack.sim.daily-report.large_track_lcff0001_simulator_200k_v1`
- `com.cashalpha.v3.largetrack.sim.weekly-report.large_track_lcff0001_simulator_200k_v1`
- `com.cashalpha.v3.largetrack.sim.paper.large_track_lcff0001_simulator_200k_v1`

## Commands Applied

- `launchctl bootout gui/501 <plist>` for the loaded V3 simulation jobs
- `launchctl disable gui/501/<label>` for each V3 simulation job

## Verification

- The V3 simulation jobs are no longer present in `launchctl print gui/501/<label>`.
- The labels appear as `disabled` in `launchctl print-disabled gui/501`.
- `com.cashalpha.v3.smalltrack.real.guard` was intentionally left loaded and unchanged.

## Re-enable Procedure

Only re-enable if V3 simulation reporting is explicitly needed again:

```sh
launchctl enable gui/501/<label>
launchctl bootstrap gui/501 /Users/zhangkun/Library/LaunchAgents/<plist>
```
