# 2026-05-20 Dirty Worktree Cleanup Archive

Purpose: preserve unrelated historical worktree changes before continuing the V6AB paper-sim / alpha-improvement workstream.

This archive was created after V6AB paper simulation was launched and the system docs were synchronized. The archived files were not part of the active V6AB execution path.

## Contents

- `untracked_files/`: previously held untracked research scripts, reports, generated data, and local experiment folders. It was about `1.0G` and mostly generated historical outputs, so it was deleted after preserving `untracked_files_manifest.txt`.
- `untracked_files_manifest.txt`: original untracked-file manifest before the move.
- `tracked_patch/tracked_changed_files.txt`: tracked files that had local modifications before cleanup.
- `tracked_patch/tracked_changes_20260520.patch`: full patch preserving those tracked-file modifications.
- `move_untracked_to_archive.py` / `move_remaining_untracked_to_archive.py`: one-off scripts used to preserve original relative paths while moving untracked files.

## Deletion Follow-Up

After review, the large local `untracked_files/` payload was deleted. The manifest and tracked patch remain as the audit trail.

## Operating Decision

- Do not continue these archived branches unless a future task explicitly needs them.
- V6-A remains on the `5k` real manual pilot.
- V6AB `50k` paper simulation is the active V6 complete-system validation path.
- Future work should compare improvements against `V6AB_SIM_CANDIDATE_V2_DYNAMIC_B_SIZING`.
