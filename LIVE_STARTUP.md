# Live Startup Status

The old Iron Condor live startup path is retired and its scripts have been removed.

Do not start:

- `main_ic_us.py`
- `scheduler.py`
- `start_scheduler.sh`
- `ic_monitor.py`
- `ic_execution_guard.py`

Current live/paper status:

- `V6-A`: small real manual pilot only, guarded by release gate, managed state, reconciliation, and user monitoring.
- `V6AB`: `50k` Futu SIMULATE account paper simulation; reconcile fills before treating submitted orders as positions.

Operational entry points:

- `README_CURRENT.md`
- `SYSTEM_OVERVIEW.html`
- `V6_STRATEGY_LAB.md`
